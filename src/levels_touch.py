"""
터치 기반 지지/저항 + 회귀 평행 채널.

- touch_levels(): 실제로 여러 번 반응(터치)한 가격대만 지지/저항으로.
  스윙 고/저점(피벗)을 가까운 것끼리 묶고, 묶음 안 피벗 수 = 터치 횟수(신뢰도).
  "지표선"보다 눈에 보이는 근거(과거 반응 지점)라 직관적.
- regression_channel(): 로그 회귀 ±kσ 평행 채널. 큰 그림 추세 + 현재 채널 내 위치(%).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _swing_pivots(df: pd.DataFrame, k: int = 5) -> list[tuple[int, float]]:
    """좌우 k봉보다 높/낮은 국소 고점·저점 (위치, 가격) 목록."""
    h = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float)
    n = len(df)
    piv: list[tuple[int, float]] = []
    for i in range(k, n - k):
        if h[i] == h[i - k:i + k + 1].max():
            piv.append((i, float(h[i])))
        if lo[i] == lo[i - k:i + k + 1].min():
            piv.append((i, float(lo[i])))
    return piv


def touch_levels(df: pd.DataFrame, k: int = 5, tol: float = 0.025,
                 min_touches: int = 2, max_each: int = 3) -> dict:
    """
    터치 기반 지지/저항. 반환:
      {'price': 현재가,
       'supports': [{price, touches, members(위치 리스트), dist_pct}, ...],  (터치 많은 순)
       'resistances': [...]}
    """
    if df is None or len(df) < 2 * k + 5:
        return {"price": None, "supports": [], "resistances": []}
    cur = float(df["close"].iloc[-1])
    piv = _swing_pivots(df, k)
    if not piv:
        return {"price": cur, "supports": [], "resistances": []}

    # 가격 가까운 피벗끼리 클러스터링 → 터치 횟수
    piv_sorted = sorted(piv, key=lambda x: x[1])
    clusters: list[list[tuple[int, float]]] = [[piv_sorted[0]]]
    for p in piv_sorted[1:]:
        if (p[1] - clusters[-1][-1][1]) / p[1] <= tol:
            clusters[-1].append(p)
        else:
            clusters.append([p])

    levels = []
    for cl in clusters:
        if len(cl) < min_touches:
            continue
        price = float(np.mean([p[1] for p in cl]))
        levels.append({
            "price": price,
            "touches": len(cl),
            "members": [p[0] for p in cl],
            "dist_pct": round((price - cur) / cur * 100, 1) if cur else 0.0,
        })

    res = sorted([l for l in levels if l["price"] > cur],
                 key=lambda l: l["touches"], reverse=True)[:max_each]
    sup = sorted([l for l in levels if l["price"] < cur],
                 key=lambda l: l["touches"], reverse=True)[:max_each]
    return {"price": cur, "supports": sup, "resistances": res}


def regression_channel(df: pd.DataFrame, num_std: float = 2.0) -> dict | None:
    """
    로그 회귀 평행 채널. 반환:
      {mid, upper, lower: np.ndarray (종가와 정렬),
       position: 현재 채널 내 위치(%) 0=하단 100=상단(범위 밖이면 <0 또는 >100),
       slope_per_bar_pct: 1봉당 평균 상승률(%), trend: '상승'/'하락'/'횡보'}
    데이터 부족/유효하지 않으면 None.
    """
    if df is None or len(df) < 20:
        return None
    c = df["close"].to_numpy(float)
    if (c <= 0).any():
        return None
    x = np.arange(len(c))
    ly = np.log(c)
    slope, intercept = np.polyfit(x, ly, 1)
    line = slope * x + intercept
    std = float((ly - line).std())
    mid = np.exp(line)
    upper = np.exp(line + num_std * std)
    lower = np.exp(line - num_std * std)
    rng = upper[-1] - lower[-1]
    position = float((c[-1] - lower[-1]) / rng * 100) if rng else 50.0
    slope_pct = float((np.exp(slope) - 1) * 100)  # 1봉당 %
    trend = "상승" if slope_pct > 0.05 else "하락" if slope_pct < -0.05 else "횡보"
    return {"mid": mid, "upper": upper, "lower": lower,
            "position": position, "slope_per_bar_pct": slope_pct, "trend": trend}
