"""
알림 엔진.

  A1) 신호 변화 알림: 종목의 종합 신호 '밴드'가 바뀌면 텔레그램 발송
       (예: 중립 → 상승 우세, 상승 우세 → 강한 상승 우세)
  A2) 목표가/손절가 알림: 현재가가 사용자가 정한 목표가↑ / 손절가↓ 를 통과하면 발송

상태(data/alert_state.json)에 직전 밴드/가격을 저장해 '바뀐 순간'에만 1회 알린다.
처음 보는 종목은 조용히 상태만 기록(첫 실행 도배 방지).
"""
from __future__ import annotations

import json
from pathlib import Path

from . import notify, prices, signals

_PROJECT = Path(__file__).resolve().parent.parent
_DATA = _PROJECT / "data"
WATCHLIST_FILE = _DATA / "watchlist.json"
PORTFOLIO_FILE = _DATA / "portfolio.json"
ALERTS_FILE = _DATA / "alerts.json"          # 사용자 설정 (목표가/손절가/신호알림)
STATE_FILE = _DATA / "alert_state.json"      # 런타임 상태 (gitignore)


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def band_of(up_pct: float | None) -> tuple[str, str]:
    """up_pct -> (밴드키, 한글라벨)."""
    if up_pct is None:
        return "none", "신호 없음"
    if up_pct >= 70:
        return "strong_bull", "강한 상승 우세"
    if up_pct >= 55:
        return "bull", "상승 우세"
    if up_pct > 45:
        return "neutral", "중립"
    if up_pct > 30:
        return "bear", "하락 우세"
    return "strong_bear", "강한 하락 우세"


def _key(symbol: str, market: str) -> str:
    return f"{symbol}|{market}"


def _fmt_price(v: float, market: str) -> str:
    if v is None:
        return "-"
    return f"${v:,.2f}" if market.upper() == "US" else f"{v:,.0f}원"


def _monitored() -> dict:
    """감시 대상 {key: {name, symbol, market}} (워치리스트 + 포트폴리오 + 알림설정)."""
    out: dict = {}
    for item in _load(WATCHLIST_FILE, []) + _load(PORTFOLIO_FILE, []):
        sym, mkt = str(item.get("symbol", "")).strip(), str(item.get("market", "")).strip().upper()
        if sym and mkt:
            out[_key(sym, mkt)] = {"name": item.get("name", sym), "symbol": sym, "market": mkt}
    for k in _load(ALERTS_FILE, {}):
        if k not in out and "|" in k:
            sym, mkt = k.split("|", 1)
            out[k] = {"name": sym, "symbol": sym, "market": mkt}
    return out


def run_once(send_telegram: bool = True) -> list[str]:
    """한 번 점검하고 변화가 있으면 알림 발송. 발송(또는 발송예정) 메시지 목록 반환."""
    alerts_cfg = _load(ALERTS_FILE, {})
    state = _load(STATE_FILE, {})
    monitored = _monitored()
    messages: list[str] = []

    for k, info in monitored.items():
        sym, mkt, name = info["symbol"], info["market"], info["name"]
        cfg = alerts_cfg.get(k, {})
        df = prices.get_ohlcv(sym, mkt, "1y")
        cur = prices.get_current_price(sym, mkt)
        if df.empty or cur is None:
            continue

        res = signals.evaluate(df)
        band_key, band_label = band_of(res.get("up_pct"))
        prev = state.get(k, {})
        first_seen = not prev

        # --- A1: 신호 변화 ---
        signal_on = cfg.get("signal_alert", True)  # 기본 켜짐
        if signal_on and not first_seen:
            prev_band = prev.get("band")
            if prev_band and prev_band != band_key and band_key != "none":
                _, prev_label = band_of_label(prev_band)
                arrow = "📈" if _band_rank(band_key) > _band_rank(prev_band) else "📉"
                messages.append(
                    f"{arrow} [신호 변화] {name} ({sym})\n"
                    f"{prev_label} → {band_label} (상승우세 {res['up_pct']:.0f}%)\n"
                    f"현재가 {_fmt_price(cur, mkt)}"
                )

        # --- A2: 목표가 / 손절가 ---
        prev_price = prev.get("price")
        target = cfg.get("target")
        stop = cfg.get("stop")
        if not first_seen and prev_price is not None:
            if target and prev_price < target <= cur:
                messages.append(
                    f"🎯 [목표가 도달] {name} ({sym})\n"
                    f"목표 {_fmt_price(target, mkt)} 도달 — 현재가 {_fmt_price(cur, mkt)}"
                )
            if stop and prev_price > stop >= cur:
                messages.append(
                    f"🛑 [손절가 도달] {name} ({sym})\n"
                    f"손절 {_fmt_price(stop, mkt)} 이탈 — 현재가 {_fmt_price(cur, mkt)}"
                )

        state[k] = {"band": band_key, "price": cur}

    _save(STATE_FILE, state)

    if send_telegram and messages:
        for msg in messages:
            notify.send(msg)

    return messages


def _band_rank(band_key: str) -> int:
    return {"strong_bear": 0, "bear": 1, "none": 2, "neutral": 2, "bull": 3, "strong_bull": 4}.get(band_key, 2)


def band_of_label(band_key: str) -> tuple[str, str]:
    labels = {
        "strong_bull": "강한 상승 우세", "bull": "상승 우세", "neutral": "중립",
        "bear": "하락 우세", "strong_bear": "강한 하락 우세", "none": "신호 없음",
    }
    return band_key, labels.get(band_key, band_key)
