"""
매수 관심구간(entry zone) 자동 산출.

"현재가 바로 아래 지지선 하나"는 매수자리가 아니다. 노이즈에 가깝고,
하락추세 종목에도 태연히 자리를 찍어준다. 그래서 해외 대시보드들이 공통으로 쓰는
5가지를 겹쳐서 '점수 붙은 구간'을 만든다.

  1) 합류(confluence) — 여러 근거가 한 가격대에 모이면 하나의 '구간'으로 묶는다.
                        근거 1개짜리 선은 버린다.
  2) 거래량 검증       — 실제로 물량이 많이 오간 가격대(고거래량대)가 진짜 지지.
  3) 검증 횟수         — 과거에 그 구간을 몇 번 건드렸고 몇 번 튕겼는지.
  4) ATR               — 구간의 '폭'과 손절 위치를 변동성으로 정한다.
  5) 추세 필터         — 눌림목 매수는 상승추세에서만 통한다. 장기 이평선 아래면 추천하지 않는다.

반환은 항상 dict. 추천할 자리가 없으면 ok=False 와 사유(reason)를 담아 돌려준다.
"조용히 아무 값이나 내놓는 것"보다 "지금은 없다"고 말하는 쪽이 안전하다.

--- 검증 결과 (2026-07-28, 유니버스 91종목 × 5년, 36,094 표본) ---
규칙 = 추세 ON + 구간 진입 + RSI(2) <= 10, 신호 124건

              10일 보유 평균    승률
  비교군(아무 날)   +1.03%      53.1%
  이 규칙          +2.75%      61.3%   차이 +1.71%p, 순열검정 p=0.013

조건을 하나씩 떼보면 각각으로는 효과가 없다 — 구간만(p=0.365), RSI2만(p=0.281).
셋이 겹칠 때만 유의미하게 나온다. 20일 보유는 초과수익이 사라진다(+0.02%p, p=0.486).
즉 이건 단기 반등 신호지 장기 진입 신호가 아니다.

주의: 여러 조합을 본 뒤 고른 기준이라 다중비교를 감안하면 p=0.013은 확정적이지 않다.
표본도 124건으로 작다. "참고용 신호"이지 예측이 아니다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import indicators as ind
from . import levels as lv

# --- 튜닝 파라미터 (한곳에 모아둠) ---
CLUSTER_TOL = 0.0075   # 이 비율(0.75%) 안에 있는 레벨은 같은 구간으로 묶음
ABOVE_TOL = 0.005      # 구간 중심이 현재가보다 이만큼 넘게 위면 지지가 아님(=저항)
MAX_DIST = 0.18        # 현재가에서 18% 넘게 먼 구간은 당장 쓸모없음
ATR_WIN = 14
STOP_ATR_MULT = 1.5    # 손절 = 구간 하단 - 1.5 x ATR
ZONE_ATR_MULT = 0.5    # 구간 최소 폭 = 0.5 x ATR
MIN_SCORE = 60         # 이 점수 미만이면 추천하지 않음
MIN_RR = 2.0           # 손익비 2:1 미만이면 경고 표시
VP_BINS = 60           # 거래량 프로파일 구간 수
VP_LOOKBACK = 250      # 거래량 프로파일 산출 기간(봉)
TOUCH_LOOKBACK = 250
BOUNCE_WINDOW = 5      # 구간 터치 후 이 봉 수 안에 회복하면 '튕김'으로 인정
REARM_PCT = 0.03       # 접촉으로 다시 세려면 구간 위로 이만큼(3%)은 올라갔어야 함
BOUNCE_PCT = 0.02      # 반등 인정 기준 — 구간 상단 위로 2% 이상 회복
TARGET_MIN_GAP = 0.03  # 목표가는 구간 중심에서 최소 이만큼 위여야 의미가 있음

# 점수 배분 (거래량 데이터가 없으면 나머지로 재분배)
W_CONFLUENCE = 40
W_VOLUME = 30
W_TOUCH = 20
W_TREND = 10


def atr(df: pd.DataFrame, window: int = ATR_WIN) -> float | None:
    """Average True Range (변동성). 실패 시 None."""
    try:
        h, l, c = df["high"], df["low"], df["close"]
        pc = c.shift(1)
        tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
        v = tr.rolling(window).mean().dropna()
        return float(v.iloc[-1]) if not v.empty else None
    except Exception:
        return None


def _trend_ma(df: pd.DataFrame) -> tuple[float | None, str]:
    """추세 판단용 장기 이평선. 200일선 우선, 데이터 부족하면 120일선."""
    for win, label in ((200, "200일선"), (120, "120일선")):
        s = ind.sma(df["close"], win).dropna()
        if len(s) >= 5:
            return float(s.iloc[-1]), label
    return None, ""


def volume_profile(df: pd.DataFrame, bins: int = VP_BINS,
                   lookback: int = VP_LOOKBACK) -> tuple[np.ndarray, np.ndarray] | None:
    """일봉으로 만든 근사 거래량 프로파일 (가격대별 거래량).

    각 봉의 거래량을 그 봉의 고가~저가 구간에 균등 분배한다.
    (일봉만 있으므로 진짜 틱 단위 프로파일은 아니고 근사치)
    반환: (구간 중앙가 배열, 구간별 거래량 배열) | None
    """
    try:
        w = df.tail(lookback)
        if "volume" not in w or float(w["volume"].sum()) <= 0:
            return None                      # FX 등 거래량 없는 종목
        lo, hi = float(w["low"].min()), float(w["high"].max())
        if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
            return None
        edges = np.linspace(lo, hi, bins + 1)
        centers = (edges[:-1] + edges[1:]) / 2
        vol = np.zeros(bins)
        for _, row in w.iterrows():
            bl, bh, bv = float(row["low"]), float(row["high"]), float(row["volume"])
            if bv <= 0 or bh < bl:
                continue
            i0 = max(0, int(np.searchsorted(edges, bl, side="right") - 1))
            i1 = min(bins - 1, int(np.searchsorted(edges, bh, side="right") - 1))
            n = i1 - i0 + 1
            if n <= 0:
                continue
            vol[i0:i1 + 1] += bv / n         # 봉 범위에 균등 분배
        return centers, vol
    except Exception:
        return None


def _volume_score(vp, low: float, high: float) -> float:
    """구간이 고거래량대에 걸쳐 있으면 높은 점수 (0~1). 거래량 없으면 None."""
    if vp is None:
        return None
    centers, vol = vp
    if vol.max() <= 0:
        return None
    inside = vol[(centers >= low) & (centers <= high)]
    if inside.size == 0:
        return 0.0
    # 구간 내 최대 거래량 / 전체 최대(POC) — POC에 걸치면 1.0
    return float(min(1.0, inside.max() / vol.max()))


def _touch_score(df: pd.DataFrame, low: float, high: float) -> tuple[float, int, int]:
    """과거에 이 구간을 '위에서 내려와' 몇 번 건드렸고 몇 번 튕겼는지.

    구간 아래에서 오래 머문 기간을 접촉으로 세면 안 된다(그건 지지가 아니라 저항이었던 것).
    그래서 상태기계로 '위에 있다가 내려와 닿은 경우'만 1회로 센다.
    반환: (점수 0~1, 접촉수, 반등수)
    """
    try:
        w = df.tail(TOUCH_LOOKBACK).reset_index(drop=True)
        lows, closes = w["low"].to_numpy(), w["close"].to_numpy()
        n = len(w)
        touches = bounces = 0
        armed = False               # 구간 위에 있을 때만 '내려올 준비' 상태
        rearm = high * (1 + REARM_PCT)               # 구간 근처 횡보는 접촉으로 세지 않음
        recover = high * (1 + BOUNCE_PCT)
        i = 0
        while i < n:
            if not armed:
                if closes[i] > rearm:
                    armed = True
                i += 1
                continue
            if lows[i] <= high:                      # 위에서 내려와 구간에 닿음
                touches += 1
                end = min(n, i + BOUNCE_WINDOW + 1)
                if np.any(closes[i:end] > recover):
                    bounces += 1
                armed = False                        # 3% 위로 다시 올라가야 재무장
                i += 1
            else:
                i += 1
        if touches == 0:
            return 0.0, 0, 0
        rate = bounces / touches
        # 접촉이 3회 이상이면 가중 만점. 잘 튕겼을수록 높음.
        return float(min(1.0, touches / 3) * rate), touches, bounces
    except Exception:
        return 0.0, 0, 0


def _cluster(supports: list[dict], cur: float) -> list[dict]:
    """가까운 지지 레벨들을 하나의 구간으로 묶는다."""
    items = sorted((s for s in supports if s.get("price")), key=lambda x: x["price"])
    out: list[dict] = []
    for it in items:
        p = float(it["price"])
        lbl = str(it.get("label", "지지"))
        if out and (p - out[-1]["high"]) / cur <= CLUSTER_TOL:
            out[-1]["high"] = p
            out[-1]["labels"].append(lbl)
        else:
            out.append({"low": p, "high": p, "labels": [lbl]})
    # 라벨 정리 (levels.py 가 "20일선, 피보 0.5" 처럼 합쳐둔 경우 분해)
    for z in out:
        flat: list[str] = []
        for l in z["labels"]:
            flat += [x.strip() for x in l.split(",") if x.strip()]
        z["labels"] = list(dict.fromkeys(flat))
    return out


def compute_entry_zone(df: pd.DataFrame, cur: float | None = None,
                       min_score: int | None = None, require_trend: bool = True) -> dict:
    """매수 관심구간 산출. 항상 dict 반환 (ok=False면 reason 확인).

    min_score / require_trend 는 백테스트에서 기준을 바꿔가며 검증하려고 열어둔 것.
    운영에서는 기본값(MIN_SCORE, 추세 필터 ON)을 쓴다.
    """
    min_score = MIN_SCORE if min_score is None else min_score
    base = {"ok": False, "reason": "데이터 부족", "score": 0, "factors": []}
    try:
        if df is None or df.empty or len(df) < 60:
            return base
        cur = float(cur) if cur else float(df["close"].iloc[-1])
        a = atr(df)
        if not a or a <= 0:
            return {**base, "reason": "변동성 계산 불가"}

        # --- 5) 추세 필터: 장기 이평선 아래면 눌림목 매수 대상이 아님 ---
        ma, ma_label = _trend_ma(df)
        if ma is None:
            return {**base, "reason": "추세 판단 불가 (데이터 짧음)"}
        trend_ok = cur >= ma
        if require_trend and not trend_ok:
            return {**base, "reason": f"하락추세 ({ma_label} 아래) — 매수자리 추천 안 함",
                    "trend_ok": False}

        all_ind = ind.compute_all(df)
        supports = lv.compute_levels(df, all_ind, max_each=12).get("supports") or []
        supports = [s for s in supports if float(s["price"]) < cur]
        if not supports:
            return {**base, "reason": "현재가 아래 지지 근거 없음", "trend_ok": trend_ok}

        vp = volume_profile(df)
        zones = _cluster(supports, cur)
        scored = []
        for z in zones:
            low, high = z["low"], z["high"]
            # 구간이 너무 얇으면 ATR 폭으로 벌려준다 (매수자리는 선이 아니라 띠)
            if (high - low) < a * ZONE_ATR_MULT:
                mid = (high + low) / 2
                low, high = mid - a * ZONE_ATR_MULT / 2, mid + a * ZONE_ATR_MULT / 2
            mid = (low + high) / 2
            dist = (cur - mid) / cur
            # 구간은 현재가 아래(또는 현재가가 그 안에 있는 자리)여야 지지다.
            # 거리 하한을 두지 않는 이유: 현재가가 구간 안에 들어와 있는 상태가 곧 매수 타이밍이라
            # "너무 가깝다"고 걸러버리면 정작 신호가 떠야 할 순간을 버리게 된다.
            if dist < -ABOVE_TOL or dist > MAX_DIST:
                continue

            factors = z["labels"]
            conf = min(len(factors), 4) / 4                 # 1) 합류
            vsc = _volume_score(vp, low, high)              # 2) 거래량
            tsc, touches, bounces = _touch_score(df, low, high)  # 3) 검증 횟수

            if vsc is None:                                  # 거래량 없는 종목 → 배점 재분배
                w_c, w_v, w_t = W_CONFLUENCE + 18, 0, W_TOUCH + 12
                vsc = 0.0
            else:
                w_c, w_v, w_t = W_CONFLUENCE, W_VOLUME, W_TOUCH
            score = conf * w_c + vsc * w_v + tsc * w_t + W_TREND  # 5) 추세부합(통과했으므로 만점)

            scored.append({
                "low": low, "high": high, "mid": mid, "score": int(round(score)),
                "factors": factors, "dist_pct": -dist * 100,
                "touches": touches, "bounces": bounces,
                "vol_ratio": round(vsc, 2),
            })

        if not scored:
            return {**base, "reason": "쓸만한 거리의 지지 구간 없음", "trend_ok": trend_ok}

        # 현재가가 들어와 있는 구간이 있으면 그게 지금 행동 가능한 자리 → 우선.
        # 없으면 점수 최고 구간(= 다음에 노려볼 자리).
        here = [z for z in scored if z["low"] <= cur <= z["high"]]
        best = max(here or scored, key=lambda z: z["score"])
        if best["score"] < MIN_SCORE:
            return {**base, "reason": f"근거 부족 (최고 {best['score']}점 < {min_score}점)",
                    "trend_ok": trend_ok, "score": best["score"]}

        # --- 4) ATR 기반 손절 + 손익비 ---
        stop = best["low"] - a * STOP_ATR_MULT
        # 목표가는 구간 중심에서 충분히 떨어진 첫 저항 (바로 위 미세 레벨은 의미 없음)
        res = lv.compute_levels(df, all_ind, max_each=8).get("resistances") or []
        floor_px = best["mid"] * (1 + TARGET_MIN_GAP)
        target = next((float(r["price"]) for r in res if float(r["price"]) >= floor_px), None)
        risk = best["mid"] - stop
        rr = round((target - best["mid"]) / risk, 1) if (target and risk > 0) else None

        return {
            "ok": True, "reason": "", "trend_ok": trend_ok,
            "low": best["low"], "high": best["high"], "mid": best["mid"],
            "score": best["score"], "factors": best["factors"],
            "dist_pct": best["dist_pct"],
            "stop": stop, "stop_pct": (stop - cur) / cur * 100,
            "target": target, "rr": rr, "rr_ok": (rr is not None and rr >= MIN_RR),
            "atr": a, "touches": best["touches"], "bounces": best["bounces"],
            "vol_ratio": best["vol_ratio"],
        }
    except Exception as e:
        return {**base, "reason": f"산출 오류: {e}"}


def in_zone(zone: dict, price: float) -> bool:
    """현재가가 매수 관심구간 안에 들어왔는지."""
    return bool(zone.get("ok")) and zone["low"] <= price <= zone["high"]


def is_oversold(df: pd.DataFrame, rsi2_max: float = 10, rsi14_max: float = 40) -> bool:
    """단기 과매도 여부 — 구간 진입 '타이밍' 확인용.

    Connors RSI(2) 계열: 상승추세 안에서 단기 과매도일 때 눌림목 매수가 통한다.
    기준 10은 임의값이 아니라 백테스트로 고른 값 — 25로 완화하면 초과수익이 절반으로
    줄고, 조건을 아예 빼면 사라진다(모듈 상단 검증 결과 참고).
    RSI(2)가 안 잡히면 RSI(14)로 폴백.
    """
    try:
        r2 = ind.rsi(df["close"], 2).dropna()
        if not r2.empty:
            return bool(float(r2.iloc[-1]) <= rsi2_max)
        r14 = ind.rsi(df["close"], 14).dropna()
        return bool(not r14.empty and float(r14.iloc[-1]) <= rsi14_max)
    except Exception:
        return False


def format_zone(zone: dict, fmt_price, prefix: str = "🟢 매수 관심구간") -> list[str]:
    """알림/브리핑용 표시 줄 목록. fmt_price 는 통화 포맷 함수."""
    if not zone.get("ok"):
        return []
    lines = [
        f"{prefix}  {zone['score']}/100",
        f"{fmt_price(zone['low'])} ~ {fmt_price(zone['high'])} ({zone['dist_pct']:+.1f}%)",
    ]
    if zone.get("factors"):
        lines.append("근거: " + " · ".join(zone["factors"][:4]))
    if zone.get("touches"):
        lines.append(f"과거 {zone['touches']}회 접촉 / {zone['bounces']}회 반등")
    tail = f"손절 {fmt_price(zone['stop'])} ({zone['stop_pct']:+.1f}%)"
    if zone.get("rr"):
        tail += f" · 손익비 {zone['rr']}:1" + ("" if zone.get("rr_ok") else " ⚠️낮음")
    lines.append(tail)
    return lines
