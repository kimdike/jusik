"""
종합 총평 + 컨센서스 괴리 해석 + 진입(지지/저항) 해석.

목표: 예측기가 아니라 "현재 기술적 위치와 컨센서스 괴리를 빠르게 파악하는 보조 도구".
톤: 단정 금지("매수/매도하세요" X). "가능성이 있습니다 / 해석될 수 있습니다 /
주의가 필요합니다 / 확인 후 접근이 안전합니다" 같은 표현 사용.
규칙 기반(결정적) — LLM 호출 없음.
"""
from __future__ import annotations

REC_KO = {
    "strong_buy": "적극 매수", "buy": "매수", "hold": "중립(보유)",
    "underperform": "매도 우위", "sell": "매도", "strong_sell": "적극 매도",
    "outperform": "매수 우위",
}


def _fmt(v, market: str) -> str:
    if v is None:
        return "-"
    return f"${v:,.2f}" if market == "US" else f"{v:,.0f}원"


def rec_label(rec_key: str | None) -> str:
    return REC_KO.get(rec_key or "", "")


def _detail(votes: list, name: str) -> str | None:
    for v in votes:
        if v["name"] == name:
            return v["detail"]
    return None


# 신호등 색
TRAFFIC = {
    "good": ("🟢", "#16A34A"), "mid": ("🟡", "#CA8A04"),
    "caution": ("🟠", "#EA580C"), "bad": ("🔴", "#DC2626"),
}


def _last_val(series):
    if series is None:
        return None
    s = series.dropna()
    return float(s.iloc[-1]) if not s.empty else None


# ---------------------------------------------------------------------------
# 결론 3카드: 현재 상태(추세) / 진입 매력도 / 위험도
# ---------------------------------------------------------------------------
def verdict_cards(result: dict, levels: dict, all_ind: dict, market: str) -> list[dict]:
    votes = result.get("votes", [])
    up = result.get("up_pct")
    up = 50.0 if up is None else up
    rv = _last_val(all_ind.get("rsi"))
    ma = _detail(votes, "이동평균 배열") or ""

    # 1) 현재 상태 (추세)
    if "정배열" in ma:
        t_lv, t_lb = "good", "상승 추세"
        t_tx = "현재 주요 이동평균선 위에서 거래되고 있으며, 장기 추세는 우상향으로 해석될 수 있습니다."
    elif "역배열" in ma:
        t_lv, t_lb = "bad", "하락 추세"
        t_tx = "현재 주요 이동평균선 아래에서 거래되고 있으며, 추세는 하락 흐름으로 해석될 수 있습니다."
    elif up >= 60:
        t_lv, t_lb = "good", "상승 우세"
        t_tx = "추세 지표가 전반적으로 상승 방향에 무게가 실려 있습니다."
    elif up <= 40:
        t_lv, t_lb = "bad", "하락 우세"
        t_tx = "추세 지표가 전반적으로 하락 방향에 무게가 실려 있습니다."
    else:
        t_lv, t_lb = "mid", "방향성 약함"
        t_tx = "추세 신호가 뚜렷하지 않아 방향 확인이 필요한 구간입니다."

    # 2) 진입 매력도
    ev = entry_view(levels, market)
    ratio = ev["ratio"]
    overbought = rv is not None and rv >= 70
    if ratio is None:
        e_lv, e_lb = "mid", "보통"
        e_tx = "지지/저항이 뚜렷하지 않아 방향 확인 후 접근이 안전합니다."
    elif ratio < 0.8 or overbought:
        e_lv, e_lb = "caution", "신중"
        e_tx = "상승 추세는 유지되더라도 가까운 저항 또는 과열 부담이 있어 신규 진입은 신중할 필요가 있습니다."
    elif ratio > 1.5:
        e_lv, e_lb = "good", "양호"
        e_tx = "하락 위험 대비 상승 여력이 다소 큰 편으로, 상대적으로 접근 매력이 있는 구간으로 해석될 수 있습니다."
    else:
        e_lv, e_lb = "mid", "보통"
        e_tx = "상승 여력과 하락 위험이 비슷한 구간으로, 방향 확인 후 접근이 안전합니다."

    # 3) 위험도
    score = 0
    if rv is not None and rv >= 70:
        score += 2
    elif rv is not None and rv >= 65:
        score += 1
    if any("과매수" in v.get("detail", "") for v in votes):
        score += 1
    if any("상단 밴드 돌파" in v.get("detail", "") for v in votes):
        score += 1
    sma20 = _last_val(all_ind.get("sma20"))
    price = levels.get("price")
    if sma20 and price:
        dev = (price - sma20) / sma20 * 100
        if dev >= 12:
            score += 2
        elif dev >= 6:
            score += 1
    if score >= 4:
        r_lv, r_lb = "bad", "높음"
    elif score >= 3:
        r_lv, r_lb = "caution", "다소 높음"
    elif score >= 1:
        r_lv, r_lb = "mid", "보통"
    else:
        r_lv, r_lb = "good", "낮음"
    if score >= 3:
        r_tx = "최근 상승폭이 크고 과매수 신호가 있어 단기 변동성 확대 가능성에 주의가 필요합니다."
    elif score >= 1:
        r_tx = "단기 변동성은 보통 수준으로 해석될 수 있습니다."
    else:
        r_tx = "현재 단기 과열 신호는 크지 않은 편입니다."

    return [
        {"title": "현재 상태", "level": t_lv, "label": t_lb, "text": t_tx},
        {"title": "진입 매력도", "level": e_lv, "label": e_lb, "text": e_tx},
        {"title": "위험도", "level": r_lv, "label": r_lb, "text": r_tx},
    ]


def weight_stars(w: float) -> tuple[str, str]:
    """가중치 -> (별점, 중요도 라벨)."""
    if w >= 1.5:
        return "★★★★★", "핵심"
    if w >= 1.0:
        return "★★★★☆", "중요"
    if w >= 0.75:
        return "★★★☆☆", "보조"
    return "★★☆☆☆", "참고"


def signal_split(result: dict) -> tuple[list[str], list[str]]:
    """긍정 신호 / 부정 신호 이름 목록."""
    pos, neg = [], []
    for v in result.get("votes", []):
        if v["signal"] == "bull":
            pos.append(f"{v['name']} 강세")
        elif v["signal"] == "bear":
            neg.append(f"{v['name']} 약세")
    return pos, neg


# ---------------------------------------------------------------------------
# 진입(지지/저항) 해석
# ---------------------------------------------------------------------------
def entry_view(levels: dict, market: str) -> dict:
    price = levels.get("price")
    res = levels.get("resistances") or []
    sup = levels.get("supports") or []
    nearest_res = res[0] if res else None
    nearest_sup = sup[0] if sup else None
    up_room = nearest_res["dist_pct"] if nearest_res else None       # +%
    down_risk = abs(nearest_sup["dist_pct"]) if nearest_sup else None  # %
    ratio = (up_room / down_risk) if (up_room and down_risk) else None

    if up_room is None:
        interp = "가까운 저항이 보이지 않는 신고가권으로, 상단은 열려 있으나 변동성에 주의가 필요합니다."
    elif down_risk is None:
        interp = "가까운 지지가 멀어 하락 시 변동성이 커질 수 있어 주의가 필요합니다."
    elif ratio is not None and ratio < 0.8:
        interp = ("저항까지의 상승 여력보다 지지까지의 하락 위험이 더 큰 구간입니다. "
                  "신규 진입보다 저항 돌파 또는 지지선 확인 후 접근이 안전합니다.")
    elif ratio is not None and ratio > 1.5:
        interp = ("하락 위험 대비 상승 여력이 다소 큰 구간으로 해석될 수 있습니다. "
                  "다만 지표는 보조 참고로만 활용이 필요합니다.")
    else:
        interp = "상승 여력과 하락 위험이 비슷한 구간으로, 방향 확인 후 접근이 안전합니다."

    return {
        "price": price,
        "res_price": nearest_res["price"] if nearest_res else None,
        "sup_price": nearest_sup["price"] if nearest_sup else None,
        "up_room": up_room, "down_risk": down_risk, "ratio": ratio,
        "interp": interp,
    }


# ---------------------------------------------------------------------------
# 컨센서스(전문가 의견) 괴리 해석
# ---------------------------------------------------------------------------
def consensus_view(fund: dict, market: str) -> dict | None:
    if not fund or not fund.get("rec_key") or not fund.get("analyst_count"):
        return None
    cur = fund.get("current")
    tm = fund.get("target_mean")
    gap = fund.get("target_upside")  # (목표가-현재가)/현재가*100
    rec = rec_label(fund.get("rec_key"))

    # 괴리율 라벨/톤
    if gap is None:
        gap_label, tone = "-", "calm"
    elif gap <= -5:
        gap_label, tone = "목표가 상회 · 과열 가능성", "warn"
    elif gap < 5:
        gap_label, tone = "목표가 근접", "calm"
    elif gap < 15:
        gap_label, tone = "완만한 상승 여력", "pos"
    else:
        gap_label, tone = "상승 여력 있음", "pos"

    # 해석 문구
    if gap is None:
        interp = f"증권사 컨센서스는 {rec}입니다."
    elif gap <= -3:
        strong = "크게 " if gap <= -10 else ""
        interp = (f"증권사 컨센서스는 {rec}이나, 현재가는 평균 목표가를 이미 {strong}상회하고 있습니다. "
                  f"이는 최근 주가 상승 속도가 애널리스트 목표가 조정 속도보다 빠르다는 의미일 수 있습니다.")
    elif gap >= 15:
        interp = (f"증권사 컨센서스는 {rec}이며, 평균 목표가까지 약 {gap:.0f}%의 상승 여력이 "
                  f"남아 있는 것으로 해석될 수 있습니다.")
    else:
        interp = f"증권사 컨센서스는 {rec}이며, 현재가가 평균 목표가에 비교적 근접해 있습니다."

    return {
        "rec": rec, "count": int(fund["analyst_count"]),
        "current": cur, "target_mean": tm,
        "target_high": fund.get("target_high"), "target_low": fund.get("target_low"),
        "gap": gap, "gap_label": gap_label, "tone": tone, "interp": interp,
    }


# ---------------------------------------------------------------------------
# 기술적 3단 총평 (추세 / 모멘텀 / 진입 리스크)  → HTML
# ---------------------------------------------------------------------------
def build_summary(result: dict, levels: dict, all_ind: dict, fund: dict, market: str) -> str:
    up = result.get("up_pct")
    if up is None:
        return "데이터가 부족해 총평을 만들 수 없어요."
    votes = result.get("votes", [])

    def line(text):
        return f'<div style="margin:2px 0 2px 2px;color:#374151">· {text}</div>'

    def sec(title, lines):
        body = "".join(line(t) for t in lines if t)
        return (f'<div style="margin-bottom:14px">'
                f'<div style="font-weight:700;color:#111827;margin-bottom:4px">{title}</div>{body}</div>')

    # 1) 추세
    trend_lines = []
    for nm in ["이동평균 배열", "골든/데드 크로스", "일목균형표", "ADX 추세", "추세선"]:
        d = _detail(votes, nm)
        if d:
            trend_lines.append(f"{nm}: {d}")
    if up >= 55:
        trend_lead = "이동평균·추세 지표는 전반적으로 상승 방향에 무게가 실려 있습니다."
    elif up <= 45:
        trend_lead = "이동평균·추세 지표는 전반적으로 하락 방향에 무게가 실려 있습니다."
    else:
        trend_lead = "추세 지표는 방향이 뚜렷하지 않은 혼조 상태입니다."

    # 2) 모멘텀
    rsi_s = all_ind.get("rsi")
    rv = float(rsi_s.dropna().iloc[-1]) if rsi_s is not None and not rsi_s.dropna().empty else None
    mom_lines = []
    if rv is not None:
        if rv >= 70:
            mom_lines.append(f"RSI {rv:.0f} — 과매수권(70 이상)으로 단기 조정 가능성에 주의가 필요합니다.")
        elif rv >= 60:
            mom_lines.append(f"RSI {rv:.0f} — 과매수권(70)에 근접하고 있어 단기 과열 여부 확인이 필요합니다.")
        elif rv <= 30:
            mom_lines.append(f"RSI {rv:.0f} — 과매도권으로 기술적 반등 가능성이 있습니다.")
        else:
            mom_lines.append(f"RSI {rv:.0f} — 중립 범위입니다.")
    for nm in ["MACD", "스토캐스틱", "볼린저밴드"]:
        d = _detail(votes, nm)
        if d:
            mom_lines.append(f"{nm}: {d}")

    # 3) 진입 리스크
    ev = entry_view(levels, market)
    risk_lines = []
    if ev["res_price"] is not None:
        risk_lines.append(f"가까운 저항 {_fmt(ev['res_price'], market)} — 상승 여력 약 +{ev['up_room']:.1f}%")
    if ev["sup_price"] is not None:
        risk_lines.append(f"가까운 지지 {_fmt(ev['sup_price'], market)} — 하락 위험 약 -{ev['down_risk']:.1f}%")
    if ev["ratio"] is not None:
        if ev["ratio"] < 0.8:
            risk_lines.append("⚠ 손익비가 불리한 구간 — 추격매수에 주의가 필요합니다.")
        risk_lines.append(ev["interp"])
    elif ev["interp"]:
        risk_lines.append(ev["interp"])

    html = (
        sec("추세", [trend_lead] + trend_lines)
        + sec("모멘텀", mom_lines)
        + sec("진입 리스크", risk_lines)
    )
    return html
