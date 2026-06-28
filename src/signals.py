"""
신호 종합 스코어 엔진.

여러 기술적 지표를 각각 '상승(bull) / 하락(bear) / 중립(neutral)' 투표로
환산한 뒤, 가중 합산해 "상승 우세 vs 하락 우세"를 수치(%)로 종합한다.

주의: 이것은 미래를 맞히는 '확률'이 아니라, 현재 지표들이 어느 방향
신호를 더 많이/강하게 내고 있는지를 점수화한 '신호 종합'이다.
투자 판단의 보조 지표로만 사용할 것.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import indicators as ind


def _last(series: pd.Series):
    """시리즈의 마지막 유효(non-NaN) 값. 없으면 None."""
    if series is None:
        return None
    s = series.dropna()
    if s.empty:
        return None
    return float(s.iloc[-1])


def _vote(name: str, signal: str, detail: str, weight: float = 1.0, strength: int = 1) -> dict:
    """strength: 1=보통 신호, 2=강한 신호 (방향과 결합해 5단계 표시)."""
    return {"name": name, "signal": signal, "detail": detail, "weight": weight, "strength": strength}


# 방향+세기 -> 5단계 라벨 (app 표시에서 공통 사용)
def level_label(signal: str, strength: int) -> str:
    if signal == "neutral":
        return "중립"
    base = "상승" if signal == "bull" else "하락"
    return f"강한 {base}" if strength >= 2 else base


def evaluate(df: pd.DataFrame) -> dict:
    """
    OHLCV DataFrame을 받아 지표별 투표 목록과 종합 스코어를 반환.

    반환 dict:
      - votes: 지표별 [{name, signal, detail, weight}]
      - bull_score / bear_score / neutral_count
      - up_pct / down_pct : 상승/하락 우세 비율 (중립 제외)
      - verdict : 사람이 읽는 한 줄 요약
      - sample_size : 사용한 봉 개수
    """
    votes: list[dict] = []
    if df is None or len(df) < 30:
        return {
            "votes": [],
            "bull_score": 0.0,
            "bear_score": 0.0,
            "neutral_count": 0,
            "up_pct": None,
            "down_pct": None,
            "verdict": "데이터 부족 (최소 30봉 필요)",
            "sample_size": 0 if df is None else len(df),
        }

    close = df["close"]
    price = _last(close)
    all_ind = ind.compute_all(df)

    # 1) 이동평균 정배열 / 역배열 -------------------------------------------
    s20, s60, s120 = _last(all_ind["sma20"]), _last(all_ind["sma60"]), _last(all_ind["sma120"])
    if None not in (price, s20, s60, s120):
        if price > s20 > s60 > s120:
            votes.append(_vote("이동평균 배열", "bull", "완전 정배열 (현재가 > 20 > 60 > 120일선)", 2.0, strength=2))
        elif price < s20 < s60 < s120:
            votes.append(_vote("이동평균 배열", "bear", "완전 역배열 (현재가 < 20 < 60 < 120일선)", 2.0, strength=2))
        elif price > s60:
            votes.append(_vote("이동평균 배열", "bull", "현재가가 60일선 위 (중기 상승)", 1.0))
        else:
            votes.append(_vote("이동평균 배열", "bear", "현재가가 60일선 아래 (중기 하락)", 1.0))

    # 2) 골든/데드 크로스 (20일선 vs 60일선 최근 교차) ----------------------
    s20s, s60s = all_ind["sma20"].dropna(), all_ind["sma60"].dropna()
    idx = s20s.index.intersection(s60s.index)
    if len(idx) >= 5:
        diff = (s20s.reindex(idx) - s60s.reindex(idx))
        recent = diff.tail(5)
        if (recent.iloc[0] <= 0) and (recent.iloc[-1] > 0):
            votes.append(_vote("골든/데드 크로스", "bull", "최근 골든크로스 (20일선이 60일선 상향 돌파)", 1.5, strength=2))
        elif (recent.iloc[0] >= 0) and (recent.iloc[-1] < 0):
            votes.append(_vote("골든/데드 크로스", "bear", "최근 데드크로스 (20일선이 60일선 하향 돌파)", 1.5, strength=2))

    # 3) RSI ----------------------------------------------------------------
    r = _last(all_ind["rsi"])
    if r is not None:
        if r >= 70:
            votes.append(_vote("RSI", "bear", f"과매수 구간 (RSI {r:.0f} ≥ 70) — 조정 가능성", 1.0, strength=2))
        elif r <= 30:
            votes.append(_vote("RSI", "bull", f"과매도 구간 (RSI {r:.0f} ≤ 30) — 반등 가능성", 1.0, strength=2))
        elif r >= 55:
            votes.append(_vote("RSI", "bull", f"상승 모멘텀 (RSI {r:.0f})", 0.5))
        elif r <= 45:
            votes.append(_vote("RSI", "bear", f"하락 모멘텀 (RSI {r:.0f})", 0.5))
        else:
            votes.append(_vote("RSI", "neutral", f"중립 (RSI {r:.0f})", 0.5))

    # 4) MACD ---------------------------------------------------------------
    macd_df = all_ind["macd"]
    m, sig, hist = _last(macd_df["macd"]), _last(macd_df["signal"]), _last(macd_df["hist"])
    if None not in (m, sig, hist):
        hist_s = macd_df["hist"].dropna()
        crossed_up = len(hist_s) >= 2 and hist_s.iloc[-2] <= 0 < hist_s.iloc[-1]
        crossed_dn = len(hist_s) >= 2 and hist_s.iloc[-2] >= 0 > hist_s.iloc[-1]
        if crossed_up:
            votes.append(_vote("MACD", "bull", "MACD 골든크로스 (시그널 상향 돌파)", 1.5, strength=2))
        elif crossed_dn:
            votes.append(_vote("MACD", "bear", "MACD 데드크로스 (시그널 하향 돌파)", 1.5, strength=2))
        elif m > sig:
            votes.append(_vote("MACD", "bull", "MACD가 시그널 위 (상승 우위)", 1.0))
        else:
            votes.append(_vote("MACD", "bear", "MACD가 시그널 아래 (하락 우위)", 1.0))

    # 5) 볼린저 밴드 %B -----------------------------------------------------
    pct_b = _last(all_ind["bollinger"]["pct_b"])
    if pct_b is not None:
        if pct_b >= 1.0:
            votes.append(_vote("볼린저밴드", "bear", "상단 밴드 돌파 (과열, 되돌림 주의)", 0.75, strength=2))
        elif pct_b <= 0.0:
            votes.append(_vote("볼린저밴드", "bull", "하단 밴드 이탈 (과매도, 반등 주의)", 0.75, strength=2))
        else:
            votes.append(_vote("볼린저밴드", "neutral", f"밴드 내부 (%B {pct_b:.2f})", 0.5))

    # 6) 스토캐스틱 ---------------------------------------------------------
    st = all_ind["stochastic"]
    k, d = _last(st["k"]), _last(st["d"])
    if None not in (k, d):
        if k >= 80:
            votes.append(_vote("스토캐스틱", "bear", f"과매수 (%K {k:.0f} ≥ 80)", 0.75, strength=2))
        elif k <= 20:
            votes.append(_vote("스토캐스틱", "bull", f"과매도 (%K {k:.0f} ≤ 20)", 0.75, strength=2))
        elif k > d:
            votes.append(_vote("스토캐스틱", "bull", "%K가 %D 위 (단기 상승)", 0.5))
        else:
            votes.append(_vote("스토캐스틱", "bear", "%K가 %D 아래 (단기 하락)", 0.5))

    # 7) 일목균형표 (구름대) ------------------------------------------------
    ichi = all_ind["ichimoku"]
    # 선행스팬은 미래로 shift 되어 현재 시점 값은 과거에 계산된 것 → 현재 구름 비교
    sa = _last(ichi["senkou_a"])
    sb = _last(ichi["senkou_b"])
    tenkan, kijun = _last(ichi["tenkan"]), _last(ichi["kijun"])
    if None not in (price, sa, sb):
        cloud_top, cloud_bot = max(sa, sb), min(sa, sb)
        if price > cloud_top:
            votes.append(_vote("일목균형표", "bull", "현재가가 구름대 위 (강세)", 1.5, strength=2))
        elif price < cloud_bot:
            votes.append(_vote("일목균형표", "bear", "현재가가 구름대 아래 (약세)", 1.5, strength=2))
        else:
            votes.append(_vote("일목균형표", "neutral", "현재가가 구름대 내부 (방향 모호)", 0.75))
    if None not in (tenkan, kijun):
        if tenkan > kijun:
            votes.append(_vote("전환선/기준선", "bull", "전환선 > 기준선 (단기 상승 신호)", 0.75))
        else:
            votes.append(_vote("전환선/기준선", "bear", "전환선 < 기준선 (단기 하락 신호)", 0.75))

    # 8) ADX + DI -----------------------------------------------------------
    adx_df = all_ind["adx"]
    adx_v, pdi, mdi = _last(adx_df["adx"]), _last(adx_df["plus_di"]), _last(adx_df["minus_di"])
    if None not in (adx_v, pdi, mdi):
        strong = adx_v >= 25
        stg = 2 if strong else 1
        if pdi > mdi:
            w = 1.25 if strong else 0.5
            votes.append(_vote("ADX 추세", "bull", f"+DI > -DI, ADX {adx_v:.0f} ({'강한' if strong else '약한'} 상승추세)", w, strength=stg))
        else:
            w = 1.25 if strong else 0.5
            votes.append(_vote("ADX 추세", "bear", f"-DI > +DI, ADX {adx_v:.0f} ({'강한' if strong else '약한'} 하락추세)", w, strength=stg))

    # 9) 추세선 (선형회귀 기울기) -------------------------------------------
    slope = all_ind["trend_slope"]
    if slope is not None:
        if slope > 0.15:
            votes.append(_vote("추세선", "bull", f"최근 20봉 우상향 (1봉당 +{slope:.2f}%)", 1.0, strength=2 if slope > 0.4 else 1))
        elif slope < -0.15:
            votes.append(_vote("추세선", "bear", f"최근 20봉 우하향 (1봉당 {slope:.2f}%)", 1.0, strength=2 if slope < -0.4 else 1))
        else:
            votes.append(_vote("추세선", "neutral", f"횡보 (기울기 {slope:.2f}%)", 0.5))

    # 10) 피보나치 위치 -----------------------------------------------------
    fib = all_ind["fibonacci"]
    if fib and price is not None and fib["high"] != fib["low"]:
        rng = fib["high"] - fib["low"]
        pos = (price - fib["low"]) / rng  # 0(저점) ~ 1(고점)
        if pos <= 0.382:
            votes.append(_vote("피보나치", "bull", f"되돌림 하단 지지권 (위치 {pos*100:.0f}%) — 반등 자리", 0.5))
        elif pos >= 0.786:
            votes.append(_vote("피보나치", "bear", f"되돌림 상단 저항권 (위치 {pos*100:.0f}%) — 저항 자리", 0.5))
        else:
            votes.append(_vote("피보나치", "neutral", f"되돌림 중간 (위치 {pos*100:.0f}%)", 0.25))

    # ---- 종합 ------------------------------------------------------------
    bull_score = sum(v["weight"] for v in votes if v["signal"] == "bull")
    bear_score = sum(v["weight"] for v in votes if v["signal"] == "bear")
    neutral_count = sum(1 for v in votes if v["signal"] == "neutral")
    total = bull_score + bear_score

    if total == 0:
        up_pct = down_pct = None
        verdict = "신호 없음 / 중립"
    else:
        up_pct = round(bull_score / total * 100, 1)
        down_pct = round(100 - up_pct, 1)
        if up_pct >= 70:
            verdict = f"상승 우세 ({up_pct:.0f}%) — 강세 신호 다수"
        elif up_pct >= 55:
            verdict = f"상승 약우세 ({up_pct:.0f}%)"
        elif up_pct > 45:
            verdict = f"중립 (상승 {up_pct:.0f}% / 하락 {down_pct:.0f}%)"
        elif up_pct > 30:
            verdict = f"하락 약우세 ({down_pct:.0f}%)"
        else:
            verdict = f"하락 우세 ({down_pct:.0f}%) — 약세 신호 다수"

    # 5단계 카운트 (강한상승/상승/중립/하락/강한하락)
    counts = {
        "strong_bull": sum(1 for v in votes if v["signal"] == "bull" and v["strength"] >= 2),
        "bull": sum(1 for v in votes if v["signal"] == "bull" and v["strength"] < 2),
        "neutral": neutral_count,
        "bear": sum(1 for v in votes if v["signal"] == "bear" and v["strength"] < 2),
        "strong_bear": sum(1 for v in votes if v["signal"] == "bear" and v["strength"] >= 2),
    }

    return {
        "votes": votes,
        "bull_score": round(bull_score, 2),
        "bear_score": round(bear_score, 2),
        "neutral_count": neutral_count,
        "counts": counts,
        "up_pct": up_pct,
        "down_pct": down_pct,
        "verdict": verdict,
        "sample_size": len(df),
    }
