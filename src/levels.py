"""
지지/저항 가격대 산출 (매수·매도 참고용).

여러 기술적 근거에서 가격 레벨을 모아, 현재가 기준으로
- 지지(support): 현재가보다 아래 → '이 가격 오면 매수 주목'
- 저항(resistance): 현재가보다 위 → '이 가격은 팔거나 돌파 확인'
로 분류해 거리(%)와 함께 돌려준다.

근거: 이동평균(20/60/120), 볼린저밴드, 일목 구름/기준선,
피보나치 되돌림, 최근 스윙 고점/저점.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import indicators as ind


def _swing_points(df: pd.DataFrame, k: int = 5, lookback: int = 120) -> tuple[list[float], list[float]]:
    """최근 lookback 봉에서 좌우 k봉 대비 국소 고점/저점(스윙) 추출."""
    w = df.tail(lookback)
    highs, lows = [], []
    h, l = w["high"].to_numpy(), w["low"].to_numpy()
    n = len(w)
    for i in range(k, n - k):
        if h[i] == max(h[i - k : i + k + 1]):
            highs.append(float(h[i]))
        if l[i] == min(l[i - k : i + k + 1]):
            lows.append(float(l[i]))
    return highs, lows


def _add(levels: list[dict], label: str, price, kind_hint: str | None = None):
    if price is None or not np.isfinite(price):
        return
    levels.append({"label": label, "price": float(price)})


def compute_levels(df: pd.DataFrame, all_ind: dict | None = None, max_each: int = 5) -> dict:
    """
    지지/저항 레벨 계산.
    반환: {
      'price': 현재가,
      'supports': [{label, price, dist_pct}, ...]  (가까운 순),
      'resistances': [...]
    }
    """
    if df is None or df.empty:
        return {"price": None, "supports": [], "resistances": []}
    if all_ind is None:
        all_ind = ind.compute_all(df)

    price = float(df["close"].iloc[-1])
    raw: list[dict] = []

    # 이동평균선 (동적 지지/저항)
    for key, lbl in [("sma20", "20일선"), ("sma60", "60일선"), ("sma120", "120일선")]:
        s = all_ind.get(key)
        if s is not None and not s.dropna().empty:
            _add(raw, lbl, s.dropna().iloc[-1])

    # 볼린저 밴드
    bb = all_ind.get("bollinger")
    if bb is not None:
        _add(raw, "볼린저 상단", bb["upper"].dropna().iloc[-1] if not bb["upper"].dropna().empty else None)
        _add(raw, "볼린저 하단", bb["lower"].dropna().iloc[-1] if not bb["lower"].dropna().empty else None)

    # 일목 구름 + 기준선
    ichi = all_ind.get("ichimoku")
    if ichi is not None:
        sa = ichi["senkou_a"].dropna()
        sb = ichi["senkou_b"].dropna()
        kj = ichi["kijun"].dropna()
        if not sa.empty:
            _add(raw, "구름 선행A", sa.iloc[-1])
        if not sb.empty:
            _add(raw, "구름 선행B", sb.iloc[-1])
        if not kj.empty:
            _add(raw, "일목 기준선", kj.iloc[-1])

    # 피보나치 되돌림
    fib = all_ind.get("fibonacci")
    if fib and fib.get("levels"):
        for name, lv in fib["levels"].items():
            _add(raw, f"피보 {name}", lv)

    # 최근 스윙 고점/저점
    highs, lows = _swing_points(df)
    # 너무 많지 않게 현재가에서 가까운 몇 개만 나중에 정렬로 추림
    for hp in highs:
        _add(raw, "스윙 고점", hp)
    for lp in lows:
        _add(raw, "스윙 저점", lp)

    # 분류 + 거리
    supports, resistances = [], []
    for lv in raw:
        dist = (lv["price"] - price) / price * 100
        item = {"label": lv["label"], "price": lv["price"], "dist_pct": round(dist, 2)}
        if lv["price"] < price:
            supports.append(item)
        elif lv["price"] > price:
            resistances.append(item)

    # 너무 가까운(±0.1%) 중복 레벨 병합
    def _dedup(items: list[dict]) -> list[dict]:
        items = sorted(items, key=lambda x: x["price"])
        out: list[dict] = []
        for it in items:
            if out and abs(it["price"] - out[-1]["price"]) / price < 0.003:
                out[-1]["label"] += f", {it['label']}"
            else:
                out.append(dict(it))
        return out

    supports = _dedup(supports)
    resistances = _dedup(resistances)

    # 현재가에서 가까운 순 정렬 후 상위 N개
    supports = sorted(supports, key=lambda x: abs(x["dist_pct"]))[:max_each]
    resistances = sorted(resistances, key=lambda x: abs(x["dist_pct"]))[:max_each]
    # 표시용으로 가격 내림차순(저항 위→아래), 지지 내림차순
    supports = sorted(supports, key=lambda x: x["price"], reverse=True)
    resistances = sorted(resistances, key=lambda x: x["price"])

    return {"price": price, "supports": supports, "resistances": resistances}
