"""
백테스트 엔진.

"이 대시보드의 종합 신호대로 매매했다면 과거 수익률이 어땠을까?"를
과거 데이터로 검증한다. 신호 신뢰도를 숫자로 보여주기 위한 모듈.

전략(롱 온리):
  - 매 봉의 '종가'까지의 데이터만 사용해 종합 신호 점수(up_pct)를 계산한다.
    (미래 정보를 쓰지 않도록 df.iloc[:i+1] 슬라이스로 평가 → 룩어헤드 방지)
  - 미보유 상태에서 up_pct >= buy_th 이면 다음 봉부터 매수 보유.
  - 보유 상태에서 up_pct <= sell_th 이면 다음 봉부터 매도 청산.
  - 신호는 종가에 계산되므로 '다음 봉'의 가격 변화부터 반영한다(현실적 체결 가정).

주의: 과거 성과가 미래 수익을 보장하지 않는다. 거래비용·슬리피지·세금은
단순화되어 있고, 표본 구간에 따라 결과가 크게 달라질 수 있다. 참고용.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import signals


def _max_drawdown(equity: np.ndarray) -> float:
    """자산곡선에서 최대 낙폭(MDD, %). 음수로 반환 (예: -23.4)."""
    if len(equity) == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    return float(dd.min() * 100)


def _cagr(equity: np.ndarray, index: pd.DatetimeIndex) -> float | None:
    """연환산 수익률(CAGR, %). 기간이 너무 짧으면 None."""
    if len(equity) < 2 or equity[0] <= 0:
        return None
    days = (index[-1] - index[0]).days
    if days < 30:
        return None
    years = days / 365.25
    total = equity[-1] / equity[0]
    if total <= 0:
        return None
    return float((total ** (1 / years) - 1) * 100)


def compute_signal_series(df: pd.DataFrame, warmup: int = 150, step: int = 1) -> pd.Series:
    """
    각 봉 시점까지의 데이터만으로 종합 신호 점수(up_pct)를 계산해 시계열로 반환.

    - warmup: 이 봉 수 이전은 지표가 안정되지 않아 평가하지 않음(NaN).
    - step: 1이면 매 봉 평가. 2 이상이면 건너뛰며 평가 후 앞으로 채움(속도용).
    룩어헤드 방지를 위해 항상 과거~현재 슬라이스만 evaluate에 넘긴다.
    """
    n = len(df)
    out = pd.Series(np.nan, index=df.index, dtype=float)
    if n == 0:
        return out
    warmup = max(warmup, 30)
    last_val = np.nan
    for i in range(n):
        if i < warmup:
            continue
        if (i - warmup) % step == 0:
            res = signals.evaluate(df.iloc[: i + 1])
            up = res.get("up_pct")
            last_val = up if up is not None else last_val
        out.iloc[i] = last_val
    return out


def run_backtest(
    df: pd.DataFrame,
    buy_th: float = 60.0,
    sell_th: float = 45.0,
    warmup: int = 150,
    fee_pct: float = 0.1,
    step: int = 1,
) -> dict:
    """
    종합 신호 기반 롱 전략을 시뮬레이션.

    Args:
      buy_th : up_pct 가 이 값 이상이면 매수 진입.
      sell_th: up_pct 가 이 값 이하이면 청산.
      warmup : 평가 시작 전 워밍업 봉 수.
      fee_pct: 1회 매매(편도) 수수료/슬리피지 가정(%). 진입·청산 각각 차감.
      step   : 신호 평가 간격(속도 조절용).

    반환 dict:
      ok, reason(실패 시),
      dates, price(정규화된 보유곡선), equity(전략 자산곡선),
      position(보유여부 0/1), signal(up_pct 시계열),
      trades[{entry_date, entry_price, exit_date, exit_price, ret_pct, bars}],
      metrics{strategy_return, buyhold_return, n_trades, win_rate,
              strategy_mdd, buyhold_mdd, strategy_cagr, buyhold_cagr,
              exposure, avg_hold_bars}
    """
    n = len(df)
    if df is None or n < warmup + 20:
        return {
            "ok": False,
            "reason": f"데이터 부족 (최소 {warmup + 20}봉 필요, 현재 {n}봉). 기간을 늘려보세요.",
        }

    close = df["close"].to_numpy(dtype=float)
    sig = compute_signal_series(df, warmup=warmup, step=step)
    sig_v = sig.to_numpy(dtype=float)

    # 1) 각 봉 종가에서 '다음 봉부터 적용할' 목표 포지션 결정
    desired = np.zeros(n, dtype=int)
    pos = 0
    for i in range(n):
        up = sig_v[i]
        if not np.isnan(up):
            if pos == 0 and up >= buy_th:
                pos = 1
            elif pos == 1 and up <= sell_th:
                pos = 0
        desired[i] = pos

    # 2) 자산곡선: 봉 i 동안의 보유여부 = 직전 봉 종가에 결정된 포지션(desired[i-1])
    fee = fee_pct / 100.0
    equity = np.ones(n, dtype=float)
    held = np.zeros(n, dtype=int)
    trades: list[dict] = []
    entry_price = entry_idx = None

    for i in range(1, n):
        hold = desired[i - 1]
        held[i] = hold
        bar_ret = (close[i] / close[i - 1] - 1) if close[i - 1] else 0.0
        eq = equity[i - 1] * (1 + bar_ret * hold)

        changed = desired[i - 1] != desired[i - 2] if i >= 2 else desired[i - 1] != 0
        # 진입/청산 발생 봉에 편도 수수료 차감
        if changed:
            eq *= (1 - fee)
        equity[i] = eq

        # 거래기록 (진입=0->1, 청산=1->0)  ※ desired[i-1] 기준 체결 시점에 맞춤
        prev2 = desired[i - 2] if i >= 2 else 0
        if desired[i - 1] == 1 and prev2 == 0:
            entry_price, entry_idx = close[i - 1], i - 1
        elif desired[i - 1] == 0 and prev2 == 1 and entry_price is not None:
            ex_price = close[i - 1]
            gross = ex_price / entry_price - 1
            net = (1 - fee) * (1 - fee) * (1 + gross) - 1  # 진입+청산 편도 수수료 반영
            trades.append({
                "entry_date": df.index[entry_idx],
                "entry_price": float(entry_price),
                "exit_date": df.index[i - 1],
                "exit_price": float(ex_price),
                "ret_pct": float(net * 100),
                "bars": int((i - 1) - entry_idx),
            })
            entry_price = entry_idx = None

    # 마지막에 보유 중이면 미실현 거래로 마감 처리
    if entry_price is not None:
        ex_price = close[-1]
        gross = ex_price / entry_price - 1
        net = (1 - fee) * (1 - fee) * (1 + gross) - 1
        trades.append({
            "entry_date": df.index[entry_idx],
            "entry_price": float(entry_price),
            "exit_date": df.index[-1],
            "exit_price": float(ex_price),
            "ret_pct": float(net * 100),
            "bars": int((n - 1) - entry_idx),
            "open": True,
        })

    # 3) 보유(Buy&Hold) 곡선 — 평가 시작 시점부터 비교 (동일 출발선)
    start = warmup
    base = close[start] if close[start] else close[0]
    buyhold = close / base

    # 전략 자산곡선도 평가 시작 시점부터 비교하도록 재정규화
    eq_from_start = equity / equity[start] if equity[start] else equity

    dates = df.index
    strat_eq = eq_from_start[start:]
    bh_eq = buyhold[start:]

    wins = [t for t in trades if t["ret_pct"] > 0]
    n_trades = len(trades)
    win_rate = (len(wins) / n_trades * 100) if n_trades else None
    exposure = float(held[start:].mean() * 100) if n > start else 0.0
    avg_hold = float(np.mean([t["bars"] for t in trades])) if trades else None

    metrics = {
        "strategy_return": float((strat_eq[-1] - 1) * 100),
        "buyhold_return": float((bh_eq[-1] - 1) * 100),
        "n_trades": n_trades,
        "win_rate": win_rate,
        "strategy_mdd": _max_drawdown(strat_eq),
        "buyhold_mdd": _max_drawdown(bh_eq),
        "strategy_cagr": _cagr(strat_eq, dates[start:]),
        "buyhold_cagr": _cagr(bh_eq, dates[start:]),
        "exposure": exposure,
        "avg_hold_bars": avg_hold,
    }

    return {
        "ok": True,
        "strategy": "signal",
        "dates": dates[start:],
        "equity": strat_eq,
        "price": bh_eq,
        "position": held[start:],
        "signal": sig_v[start:],
        "trades": trades,
        "metrics": metrics,
        "params": {"buy_th": buy_th, "sell_th": sell_th, "fee_pct": fee_pct, "warmup": warmup},
    }


def run_dip_backtest(
    df: pd.DataFrame,
    dip_pct: float = 7.0,
    take_pct: float = 10.0,
    stop_pct: float = 7.0,
    lookback: int = 20,
    max_hold: int = 60,
    fee_pct: float = 0.1,
) -> dict:
    """
    눌림목(매수자리) 전략 백테스트.

    규칙(롱 온리):
      - 진입: 최근 lookback봉 고점 대비 dip_pct% 이상 하락하면(눌림목) 매수.
      - 청산: 매수가 대비 +take_pct% 도달(익절) / -stop_pct% 이탈(손절) /
              max_hold봉 경과(시간 청산) 중 먼저 오는 것.
    "이 매수자리에 샀으면 수익률?"을 검증. 종가 기준 단순 시뮬레이션(참고용).
    """
    n = len(df)
    warmup = lookback + 1
    if df is None or n < warmup + 20:
        return {"ok": False, "reason": f"데이터 부족 (최소 {warmup + 20}봉 필요, 현재 {n}봉)."}

    close = df["close"].to_numpy(dtype=float)
    roll_high = df["close"].rolling(lookback, min_periods=lookback).max().to_numpy(dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        dd = np.where(roll_high > 0, (close / roll_high - 1) * 100, 0.0)  # 고점 대비 낙폭(%)

    # 목표 포지션 결정 (종가 기준 → 다음 봉부터 반영)
    desired = np.zeros(n, dtype=int)
    pos, ep, ei = 0, None, None
    for i in range(n):
        if i < warmup:
            continue
        if pos == 0:
            if not np.isnan(dd[i]) and dd[i] <= -dip_pct:
                pos, ep, ei = 1, close[i], i
        else:
            ret = (close[i] / ep - 1) if ep else 0.0
            if ret >= take_pct / 100 or ret <= -stop_pct / 100 or (i - ei) >= max_hold:
                pos = 0
        desired[i] = pos

    # 자산곡선 + 거래 (run_backtest와 동일 방식)
    fee = fee_pct / 100.0
    equity = np.ones(n, dtype=float)
    held = np.zeros(n, dtype=int)
    trades: list[dict] = []
    entry_price = entry_idx = None
    for i in range(1, n):
        h = desired[i - 1]
        held[i] = h
        bar_ret = (close[i] / close[i - 1] - 1) if close[i - 1] else 0.0
        eq = equity[i - 1] * (1 + bar_ret * h)
        changed = desired[i - 1] != desired[i - 2] if i >= 2 else desired[i - 1] != 0
        if changed:
            eq *= (1 - fee)
        equity[i] = eq
        prev2 = desired[i - 2] if i >= 2 else 0
        if desired[i - 1] == 1 and prev2 == 0:
            entry_price, entry_idx = close[i - 1], i - 1
        elif desired[i - 1] == 0 and prev2 == 1 and entry_price is not None:
            ex = close[i - 1]
            net = (1 - fee) * (1 - fee) * (1 + (ex / entry_price - 1)) - 1
            trades.append({"entry_date": df.index[entry_idx], "entry_price": float(entry_price),
                           "exit_date": df.index[i - 1], "exit_price": float(ex),
                           "ret_pct": float(net * 100), "bars": int((i - 1) - entry_idx)})
            entry_price = entry_idx = None
    if entry_price is not None:
        ex = close[-1]
        net = (1 - fee) * (1 - fee) * (1 + (ex / entry_price - 1)) - 1
        trades.append({"entry_date": df.index[entry_idx], "entry_price": float(entry_price),
                       "exit_date": df.index[-1], "exit_price": float(ex),
                       "ret_pct": float(net * 100), "bars": int((n - 1) - entry_idx), "open": True})

    start = warmup
    base = close[start] if close[start] else close[0]
    buyhold = close / base
    eq_from_start = equity / equity[start] if equity[start] else equity
    dates = df.index
    strat_eq = eq_from_start[start:]
    bh_eq = buyhold[start:]
    n_trades = len(trades)
    wins = [t for t in trades if t["ret_pct"] > 0]
    metrics = {
        "strategy_return": float((strat_eq[-1] - 1) * 100),
        "buyhold_return": float((bh_eq[-1] - 1) * 100),
        "n_trades": n_trades,
        "win_rate": (len(wins) / n_trades * 100) if n_trades else None,
        "strategy_mdd": _max_drawdown(strat_eq),
        "buyhold_mdd": _max_drawdown(bh_eq),
        "strategy_cagr": _cagr(strat_eq, dates[start:]),
        "buyhold_cagr": _cagr(bh_eq, dates[start:]),
        "exposure": float(held[start:].mean() * 100) if n > start else 0.0,
        "avg_hold_bars": float(np.mean([t["bars"] for t in trades])) if trades else None,
    }
    return {
        "ok": True,
        "strategy": "dip",
        "dates": dates[start:],
        "equity": strat_eq,
        "price": bh_eq,
        "position": held[start:],
        "dd": dd[start:],
        "trades": trades,
        "metrics": metrics,
        "params": {"dip_pct": dip_pct, "take_pct": take_pct, "stop_pct": stop_pct,
                   "lookback": lookback, "max_hold": max_hold, "fee_pct": fee_pct},
    }
