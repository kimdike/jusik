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
import os
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
        # 실시간 체결가 우선(주식 일봉 지연 구간 보정), 실패 시 종가 폴백
        cur = prices.get_live_quote(sym, mkt).get("price") or prices.get_current_price(sym, mkt)
        if df.empty or cur is None:
            continue

        res = signals.evaluate(df)
        up = res.get("up_pct")
        band_key, band_label = band_of(up)
        prev = state.get(k, {})
        first_seen = not prev
        cur_msgs: list[str] = []            # 반환/대시보드용 짧은 로그
        triggers: list[tuple[str, str]] = []  # (이모지, 짧은 라벨) — 캡션 헤더용
        sig_changed = False

        # --- A1: 신호 변화 ---
        if cfg.get("signal_alert", True) and not first_seen:
            pb = prev.get("band")
            if pb and pb != band_key and band_key != "none":
                arrow = "📈" if _band_rank(band_key) > _band_rank(pb) else "📉"
                sig_changed = True
                triggers.append(("🔔", f"신호 변경 → {arrow} {band_label}"))
                cur_msgs.append(f"🔔 신호변경 {name}({sym}) → {band_label}")

        # --- A2: 목표가 / 매수자리 / 손절가 (크로싱) ---
        prev_price = prev.get("price")
        target, entry, stop = cfg.get("target"), cfg.get("entry"), cfg.get("stop")
        if not first_seen and prev_price is not None:
            if target and prev_price < target <= cur:
                triggers.append(("🎯", "목표가 도달"))
                cur_msgs.append(f"🎯 목표가 {name}({sym}) {_fmt_price(target, mkt)}")
            if entry and prev_price > entry >= cur:
                triggers.append(("🟢", "매수 자리"))
                cur_msgs.append(f"🟢 매수자리 {name}({sym}) {_fmt_price(entry, mkt)}")
            if stop and prev_price > stop >= cur:
                triggers.append(("🛑", "손절가"))
                cur_msgs.append(f"🛑 손절가 {name}({sym}) {_fmt_price(stop, mkt)}")

        state[k] = {"band": band_key, "price": cur}

        if triggers:
            messages.extend(cur_msgs)
            if send_telegram:
                cap = _alert_caption(name, sym, mkt, df, cfg, up, triggers, sig_changed)
                _send_with_chart(sym, mkt, name, df, cfg, cap)

    _save(STATE_FILE, state)
    return messages


_DIV = "━━━━━━━━━━"


def _opinion(up) -> tuple[str, str]:
    """종합점수 → (이모지, 라벨). 🟢 매수 우위 / 🟡 관망 / 🔴 매도 우위."""
    if up is None:
        return "⚪", "데이터 부족"
    if up >= 60:
        return "🟢", "매수 우위"
    if up <= 40:
        return "🔴", "매도 우위"
    return "🟡", "관망"


def _price_rows(mkt: str, df, cfg: dict) -> list[str]:
    """가격 요약 표(현재/지지/저항/목표/매수/손절) — 아이콘+거리%."""
    from . import indicators as ind
    from . import levels as lv
    cur = float(df["close"].iloc[-1])

    def f(v):
        return _fmt_price(v, mkt)

    def pct(v):
        return f"({(v - cur) / cur * 100:+.1f}%)" if cur else ""

    rows = [f"현재   {f(cur)}"]
    try:
        L = lv.compute_levels(df, ind.compute_all(df))
        s = (L.get("supports") or [{}])[0]
        r = (L.get("resistances") or [{}])[0]
        if s.get("price"):
            rows.append(f"🟢 지지 {f(s['price'])} {pct(s['price'])}")
        if r.get("price"):
            rows.append(f"🔴 저항 {f(r['price'])} {pct(r['price'])}")
    except Exception:
        pass
    if cfg.get("target"):
        rows.append(f"🎯 목표 {f(cfg['target'])} {pct(cfg['target'])}")
    if cfg.get("entry"):
        rows.append(f"🟢 매수 {f(cfg['entry'])} {pct(cfg['entry'])}")
    if cfg.get("stop"):
        rows.append(f"🛑 손절 {f(cfg['stop'])} {pct(cfg['stop'])}")
    return rows


def _news_one(name: str, mkt: str) -> str:
    """관련 뉴스 1건 제목. 실패 시 빈 문자열."""
    try:
        from . import news as news_mod
        region = "US" if mkt.upper() == "US" else "KR"
        items = news_mod.get_news(name, region=region, limit=1)
        t = (items[0].get("title") or "").strip() if items else ""
        return f"📰 {t}" if t else ""
    except Exception:
        return ""


def _alert_caption(name: str, sym: str, mkt: str, df, cfg: dict, up,
                   triggers: list[tuple[str, str]], sig_changed: bool) -> str:
    """간결 알림 캡션: 결론 먼저 → 가격 요약 표 → (신호변화 시) 뉴스 1줄."""
    hdr = " · ".join(f"{e} {l}" for e, l in triggers)
    oe, ol = _opinion(up)
    up_s = f"{up:.0f}" if up is not None else "-"
    lines = [hdr, f"{name} ({sym})", "", f"{oe} {ol} ({up_s}/100)",
             _DIV, "💰 가격 요약"] + _price_rows(mkt, df, cfg)
    if sig_changed:
        nb = _news_one(name, mkt)
        if nb:
            lines += [_DIV, nb]
    return "\n".join(lines)


def _send_with_chart(sym: str, mkt: str, name: str, df, cfg: dict, caption: str) -> None:
    """그 종목 차트(지지/저항+사용자 목표가 선)를 만들어 캡션과 함께 발송. 실패 시 텍스트로 폴백."""
    import tempfile

    path = None
    try:
        from . import chartimg
        fd, path = tempfile.mkstemp(suffix=".png", prefix="alert_")
        os.close(fd)
        out = chartimg.render_chart(sym, mkt, name, path,
                                    target=cfg.get("target"), entry=cfg.get("entry"), df=df)
        if out:
            ok, _info = notify.send_photo(out, caption=caption)
            if ok:
                return
    except Exception:
        pass
    finally:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
    notify.send(caption)  # 차트 실패 시 텍스트만이라도


def build_briefing(send_telegram: bool = True) -> str:
    """워치리스트/보유 종목 전체를 신호 강한 순으로 요약한 '아침 브리핑' 텍스트.
    각 종목: 현재가·전일대비·종합신호·(설정 시) 매수자리/목표가까지 거리."""
    alerts_cfg = _load(ALERTS_FILE, {})
    monitored = _monitored()
    rows = []
    for k, info in monitored.items():
        sym, mkt, name = info["symbol"], info["market"], info["name"]
        df = prices.get_ohlcv(sym, mkt, "6mo")
        if df is None or df.empty:
            continue
        cur = float(df["close"].iloc[-1])
        prev = float(df["close"].iloc[-2]) if len(df) >= 2 else cur
        chg = (cur - prev) / prev * 100 if prev else 0.0
        res = signals.evaluate(df)
        up = res.get("up_pct")
        rows.append((up if up is not None else -1, name, mkt, cur, chg, up, alerts_cfg.get(k, {})))

    rows.sort(key=lambda r: r[0], reverse=True)  # 신호 강한 순

    lines = ["🌅 오늘의 워치리스트 브리핑", ""]
    for _, name, mkt, cur, chg, up, cfg in rows:
        _, band = band_of(up)
        arrow = "🔺" if chg > 0 else ("🔻" if chg < 0 else "▪️")
        head = f"{name}  {_fmt_price(cur, mkt)} {arrow}{chg:+.1f}%  · 신호 {up:.0f}({band})" if up is not None \
            else f"{name}  {_fmt_price(cur, mkt)} {arrow}{chg:+.1f}%  · 신호 -"
        extras = []
        if cfg.get("entry"):
            d = (cfg["entry"] - cur) / cur * 100 if cur else 0
            extras.append(f"매수자리까지 {d:+.1f}%")
        if cfg.get("target"):
            d = (cfg["target"] - cur) / cur * 100 if cur else 0
            extras.append(f"목표가까지 {d:+.1f}%")
        line = "• " + head + (("\n   " + " · ".join(extras)) if extras else "")
        lines.append(line)

    lines.append("")
    lines.append("※ 보조 지표 요약 · 투자 판단은 본인 책임")
    text = "\n".join(lines)
    if send_telegram:
        notify.send(text)
    return text


def _band_rank(band_key: str) -> int:
    return {"strong_bear": 0, "bear": 1, "none": 2, "neutral": 2, "bull": 3, "strong_bull": 4}.get(band_key, 2)


def band_of_label(band_key: str) -> tuple[str, str]:
    labels = {
        "strong_bull": "강한 상승 우세", "bull": "상승 우세", "neutral": "중립",
        "bear": "하락 우세", "strong_bear": "강한 하락 우세", "none": "신호 없음",
    }
    return band_key, labels.get(band_key, band_key)


def build_market_wrap(send_telegram: bool = True) -> str:
    """장 마감 후 '오늘의 증시' 하루 정리 — 지수·환율 → 대형주 등락 → 관전 포인트.
    (외국인/기관/개인 수급은 무료 데이터로 불가해 제외)"""
    from datetime import datetime, timedelta, timezone

    from . import market as mkt_mod
    kst = datetime.now(timezone(timedelta(hours=9)))
    idx = {d["name"]: d for d in mkt_mod.get_indices()}

    def arw(c):
        return "🔻" if (c or 0) < 0 else "🔺" if (c or 0) > 0 else "▪️"

    L = [f"🇰🇷 오늘의 증시 ({kst.month}월 {kst.day}일)", _DIV]
    for nm in ("코스피", "코스닥"):
        d = idx.get(nm)
        if d and d.get("change_pct") is not None:
            L.append(f"{arw(d['change_pct'])} {nm} {d['value']:,.2f} ({d['change_pct']:+.2f}%)")
    fx = idx.get("USD/KRW")
    if fx and fx.get("change_pct") is not None:
        L.append(f"{arw(fx['change_pct'])} 원·달러 {fx['value']:,.2f} ({fx['change_pct']:+.2f}%)")

    # 대형주 등락 (낙폭/상승폭 큰 순)
    bigs = [("삼성전자", "005930"), ("SK하이닉스", "000660"), ("현대차", "005380"),
            ("기아", "000270"), ("NAVER", "035420"), ("LG에너지솔루션", "373220"),
            ("셀트리온", "068270"), ("카카오", "035720"), ("KB금융", "105560"),
            ("현대모비스", "012330")]
    movers = []
    for nm, code in bigs:
        df = prices.get_ohlcv(code, "KR", "5d")
        if df is None or len(df) < 2:
            continue
        movers.append((nm, (float(df["close"].iloc[-1]) / float(df["close"].iloc[-2]) - 1) * 100))
    if movers:
        movers.sort(key=lambda x: x[1])
        L += [_DIV, "💥 시가총액 대형주"]
        for nm, c in movers[:5]:
            L.append(f"{arw(c)} {nm} {c:+.2f}%")

    # 해외 한 줄
    ov = []
    for nm, lbl in (("S&P 500", "S&P"), ("나스닥", "나스닥")):
        d = idx.get(nm)
        if d and d.get("change_pct") is not None:
            ov.append(f"{lbl} {d['change_pct']:+.2f}%")
    if ov:
        L += [_DIV, "🌎 해외 " + " · ".join(ov)]

    # 관전 포인트 (자동)
    pts = []
    ks = idx.get("코스피", {}).get("change_pct")
    if ks is not None and ks <= -2:
        pts.append("코스피 큰 폭 하락")
    elif ks is not None and ks >= 2:
        pts.append("코스피 큰 폭 상승")
    semi = [c for nm, c in movers if nm in ("삼성전자", "SK하이닉스")]
    if semi and sum(semi) / len(semi) <= -2:
        pts.append("반도체 대형주 약세가 지수 압박")
    elif semi and sum(semi) / len(semi) >= 2:
        pts.append("반도체 대형주 강세가 지수 견인")
    if fx and (fx.get("change_pct") or 0) > 0.3:
        pts.append("원화 약세(환율 상승)")
    if not pts:
        pts.append("특이 급변동 없이 보합권")
    L += [_DIV, "👀 관전 포인트"] + [f"• {p}" for p in pts]
    L += ["", "※ 지수·대형주 자동 요약 · 투자 판단은 본인 책임"]

    text = "\n".join(L)
    if send_telegram:
        notify.send(text)
    return text
