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

from . import entry as entry_mod
from . import notify, prices, signals

_PROJECT = Path(__file__).resolve().parent.parent
_DATA = _PROJECT / "data"
WATCHLIST_FILE = _DATA / "watchlist.json"
GROUP_WATCHLIST_FILE = _DATA / "watchlist_group.json"   # 단톡방 전용 종목 (개인 목록과 분리)
PORTFOLIO_FILE = _DATA / "portfolio.json"
ALERTS_FILE = _DATA / "alerts.json"          # 사용자 설정 (목표가/손절가/신호알림)
STATE_FILE = _DATA / "alert_state.json"      # 런타임 상태 (gitignore)
HALT_STATE_FILE = _DATA / "halt_state.json"  # 사이드카/CB 중복 알림 방지 상태 (gitignore)


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
    m = market.upper()
    if m == "US":
        return f"${v:,.2f}"
    if m == "FX":            # 원/달러 환율 등 — 소수 2자리, 원 단위
        return f"{v:,.2f}원"
    return f"{v:,.0f}원"


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

        # --- A2: 목표가 / 손절가 (사용자가 정한 값 크로싱) ---
        prev_price = prev.get("price")
        target, user_entry, stop = cfg.get("target"), cfg.get("entry"), cfg.get("stop")
        if not first_seen and prev_price is not None:
            if target and prev_price < target <= cur:
                triggers.append(("🎯", "목표가 도달"))
                cur_msgs.append(f"🎯 목표가 {name}({sym}) {_fmt_price(target, mkt)}")
            if stop and prev_price > stop >= cur:
                triggers.append(("🛑", "손절가"))
                cur_msgs.append(f"🛑 손절가 {name}({sym}) {_fmt_price(stop, mkt)}")

        # --- A3: 매수 관심구간 ---
        # 사용자가 entry 를 직접 정해뒀으면 그 값 크로싱을 그대로 쓰고,
        # 아니면 지지 합류·거래량·검증횟수·ATR·추세로 매번 다시 계산한 구간을 쓴다.
        zone = None
        now_in_zone = False
        if user_entry:
            if not first_seen and prev_price is not None and prev_price > user_entry >= cur:
                triggers.append(("🟢", "매수 자리"))
                cur_msgs.append(f"🟢 매수자리 {name}({sym}) {_fmt_price(user_entry, mkt)}")
        else:
            zone = entry_mod.compute_entry_zone(df, cur)
            now_in_zone = entry_mod.in_zone(zone, cur)
            # 구간에 '막 들어온' 순간 + 단기 과매도일 때만 1회 (구간 안에 머무는 동안 도배 방지)
            if (now_in_zone and not prev.get("in_zone") and not first_seen
                    and entry_mod.is_oversold(df)):
                triggers.append(("🟢", f"매수 관심구간 진입 ({zone['score']}점)"))
                cur_msgs.append(
                    f"🟢 매수구간 {name}({sym}) "
                    f"{_fmt_price(zone['low'], mkt)}~{_fmt_price(zone['high'], mkt)}"
                )

        state[k] = {"band": band_key, "price": cur, "in_zone": now_in_zone}

        if triggers:
            messages.extend(cur_msgs)
            if send_telegram:
                cap = _alert_caption(name, sym, mkt, df, cfg, up, triggers, sig_changed, zone)
                _send_with_chart(sym, mkt, name, df, cfg, cap)

    _save(STATE_FILE, state)
    return messages


_DIV = "━━━━━━━━━━"


def _arrow(chg) -> str:
    """등락 표시 — 텍스트 삼각형.

    이모지 삼각형은 🔺🔻 빨강 두 개뿐이라 색으로 상승/하락을 구분할 수 없고,
    파란 삼각형 이모지는 유니코드에 없다. 🔵🔴 원형은 너무 크고 무겁게 렌더링된다.
    그래서 텍스트 삼각형을 쓴다 — 크기가 본문과 맞고 방향으로 바로 구분된다.
    (텔레그램은 본문 텍스트 색을 지정할 수 없어 색상은 테마 기본값)
    """
    c = chg or 0
    # 하락만 빨간 이모지 삼각형(🔻)을 써서 색으로 갈린다.
    # 상승도 이모지로 하면 🔺 뿐인데 그것도 빨강이라 색 구분이 사라진다.
    return "▲" if c > 0 else ("🔻" if c < 0 else "―")


def _opinion(up) -> tuple[str, str]:
    """종합점수 → (이모지, 라벨). 🟢 매수 우위 / 🟡 관망 / 🔴 매도 우위."""
    if up is None:
        return "⚪", "데이터 부족"
    if up >= 60:
        return "🟢", "매수 우위"
    if up <= 40:
        return "🔴", "매도 우위"
    return "🟡", "관망"


def _price_rows(mkt: str, df, cfg: dict, cur: float | None = None) -> list[str]:
    """가격 요약 표(현재/지지/저항/목표/매수/손절) — 아이콘+거리%.
    cur 를 주면 그 값(실시간 체결가)을 '현재'와 거리% 기준으로 사용."""
    from . import indicators as ind
    from . import levels as lv
    cur = cur if cur is not None else float(df["close"].iloc[-1])

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


def _news_multi(name: str, mkt: str, limit: int = 3) -> list[str]:
    """관련 뉴스 여러 건 — 제목이 링크로 걸린 HTML 줄 목록. 실패 시 빈 목록.
    (HTML parse_mode 로 발송해야 링크가 클릭됨)"""
    import html
    try:
        from . import news as news_mod
        region = "US" if mkt.upper() == "US" else "KR"
        items = news_mod.get_news(name, region=region, limit=limit)
        out = []
        for it in items[:limit]:
            t = (it.get("title") or "").strip()
            link = (it.get("link") or "").strip()
            if not t:
                continue
            if link:
                out.append(f'📰 <a href="{html.escape(link, quote=True)}">{html.escape(t)}</a>')
            else:
                out.append(f"📰 {html.escape(t)}")
        return out
    except Exception:
        return []


def _alert_caption(name: str, sym: str, mkt: str, df, cfg: dict, up,
                   triggers: list[tuple[str, str]], sig_changed: bool,
                   zone: dict | None = None) -> str:
    """간결 알림 캡션: 결론 먼저 → 가격 요약 표 → 매수 관심구간 → (신호변화 시) 뉴스 1줄."""
    hdr = " · ".join(f"{e} {l}" for e, l in triggers)
    oe, ol = _opinion(up)
    up_s = f"{up:.0f}" if up is not None else "-"
    lines = [hdr, f"{name} ({sym})", "", f"{oe} {ol} ({up_s}/100)",
             _DIV, "💰 가격 요약"] + _price_rows(mkt, df, cfg)
    if zone and zone.get("ok"):
        lines += [_DIV] + entry_mod.format_zone(zone, lambda v: _fmt_price(v, mkt))
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


def _kst_now():
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone(timedelta(hours=9)))


# 브리핑 종류별 헤더/부제/정렬 기준
#   pre    = 장 전(08:30) 예고        — 신호 강한 순
#   open   = 장 시작 30분 후(09:30)   — 오늘 움직임 큰 순
#   hourly = 정시 점검(매시)          — 오늘 움직임 큰 순
_BRIEF_KINDS = {
    "pre":    ("🌅 장 전 브리핑", "장 열기 전 상태 · 전일 종가 기준", "signal"),
    "open":   ("🔔 장 시작 30분", "시초가 반영된 오늘 실제 흐름", "move"),
    "hourly": ("⏱ 정시 점검", None, "move"),
}


def build_briefing(send_telegram: bool = True, kind: str = "pre") -> str:
    """워치리스트/보유 종목 전체 요약 브리핑.

    kind: 'pre'(장 전 08:30) / 'open'(장 시작 30분 09:30) / 'hourly'(정시 점검)
    각 종목: 현재가·전일대비·(open이면 시가대비)·종합신호·매수 관심구간까지 거리.
    """
    title, subtitle, sort_by = _BRIEF_KINDS.get(kind, _BRIEF_KINDS["pre"])
    alerts_cfg = _load(ALERTS_FILE, {})
    monitored = _monitored()
    rows = []
    for k, info in monitored.items():
        sym, mkt, name = info["symbol"], info["market"], info["name"]
        # 1y — 매수구간 추세 필터(200일선)를 쓰려면 6개월로는 봉이 모자람
        df = prices.get_ohlcv(sym, mkt, "1y")
        if df is None or df.empty:
            continue
        # 실시간 체결가 + 전일 종가 우선(일봉 지연/건너뜀 보정), 실패 시 봉 종가 폴백
        lq = prices.get_live_quote(sym, mkt)
        cur = lq.get("price") or float(df["close"].iloc[-1])
        prev = lq.get("prev_close") or (float(df["close"].iloc[-2]) if len(df) >= 2 else cur)
        chg = (cur - prev) / prev * 100 if prev else 0.0
        up = signals.evaluate(df).get("up_pct")
        # 시가 대비 (open 브리핑에서만 표시) — 마지막 봉의 시가
        op = None
        if kind == "open":
            try:
                o = float(df["open"].iloc[-1])
                op = (cur - o) / o * 100 if o else None
            except Exception:
                op = None
        rows.append({"name": name, "mkt": mkt, "cur": cur, "chg": chg, "up": up,
                     "open_pct": op, "cfg": alerts_cfg.get(k, {}), "df": df})

    if sort_by == "move":
        rows.sort(key=lambda r: abs(r["chg"]), reverse=True)      # 많이 움직인 순
    else:
        rows.sort(key=lambda r: (r["up"] if r["up"] is not None else -1), reverse=True)

    kst = _kst_now()
    head = f"{title}  ({kst:%m월 %d일 %H:%M} KST)"
    lines = [head] + ([subtitle, ""] if subtitle else [""])

    for r in rows:
        name, mkt, cur, chg, up, cfg = r["name"], r["mkt"], r["cur"], r["chg"], r["up"], r["cfg"]
        _, band = band_of(up)
        arrow = _arrow(chg)
        up_s = f"{up:.0f}({band})" if up is not None else "-"
        line = f"• {name}  {_fmt_price(cur, mkt)} {arrow}{chg:+.1f}%  · 신호 {up_s}"
        if r["open_pct"] is not None:
            line += f"\n   시가대비 {r['open_pct']:+.1f}%"

        extras = []
        if cfg.get("entry"):
            d = (cfg["entry"] - cur) / cur * 100 if cur else 0
            extras.append(f"매수자리까지 {d:+.1f}%")
        else:
            z = entry_mod.compute_entry_zone(r["df"], cur)   # 자동 산출 매수 관심구간
            if z.get("ok"):
                extras.append(
                    f"🟢 매수구간 {_fmt_price(z['low'], mkt)}~{_fmt_price(z['high'], mkt)}"
                    f" ({z['dist_pct']:+.1f}%, {z['score']}점)"
                )
        if cfg.get("target"):
            d = (cfg["target"] - cur) / cur * 100 if cur else 0
            extras.append(f"목표가까지 {d:+.1f}%")
        if extras:
            line += "\n   " + " · ".join(extras)
        lines.append(line)

    lines += ["", "※ 보조 지표 요약 · 투자 판단은 본인 책임"]
    text = "\n".join(lines)
    if send_telegram:
        notify.send(text)
    return text


def add_watch(query: str, market: str | None = None, name: str | None = None) -> dict:
    """이름/티커로 검색해 워치리스트에 추가. 브리핑·알림 대상에 바로 반영된다.

    반환: {"ok": bool, "msg": str, "item": {...}|None, "candidates": [...]}
    """
    from . import search as search_mod
    cands = search_mod.search_symbols(query, limit=8)
    if market:
        mk = market.strip().upper()
        cands = [c for c in cands if c["market"] == mk] or cands
    if not cands:
        return {"ok": False, "msg": f"'{query}' 검색 결과 없음", "item": None, "candidates": []}

    pick = cands[0]
    item = {"name": name or pick["name"], "symbol": pick["symbol"], "market": pick["market"]}
    wl = _load(WATCHLIST_FILE, [])
    for w in wl:
        if str(w.get("symbol")) == item["symbol"] and str(w.get("market")).upper() == item["market"]:
            return {"ok": False, "msg": f"이미 있음: {w.get('name')}", "item": w, "candidates": cands}
    wl.append(item)
    _save(WATCHLIST_FILE, wl)
    return {"ok": True, "msg": f"추가됨: {item['name']} ({item['symbol']}/{item['market']})",
            "item": item, "candidates": cands}


def remove_watch(query: str) -> dict:
    """이름 또는 티커로 워치리스트에서 제거."""
    q = (query or "").strip().lower()
    wl = _load(WATCHLIST_FILE, [])
    keep, gone = [], []
    for w in wl:
        if q and (q == str(w.get("symbol", "")).lower() or q in str(w.get("name", "")).lower()):
            gone.append(w)
        else:
            keep.append(w)
    if not gone:
        return {"ok": False, "msg": f"'{query}' 워치리스트에 없음", "removed": []}
    _save(WATCHLIST_FILE, keep)
    return {"ok": True, "msg": "제거됨: " + ", ".join(f"{g.get('name')}" for g in gone), "removed": gone}


def build_chart_briefing(symbols, send_telegram: bool = True, news_n: int = 3,
                         target: str = "personal", title: str = "🌅 브리핑") -> list[str]:
    """지정 종목 각각을 '차트 + 풍부한 캡션(가격요약 + 관련뉴스 링크)'으로 발송.

    symbols: [(sym, mkt, name), ...]  (예: [("000660","KR","SK하이닉스")])
    - 현재가/등락률은 실시간 체결가 기준(get_live_quote), 일봉 폴백
    - 캡션이 1024자를 넘으면 뉴스를 별도 텍스트 메시지로 자동 분리(HTML 링크)
    - target: 'personal'(개인방) | 'group'(단톡방)
    반환: 처리 로그 목록.
    """
    import html as _html
    import tempfile
    from datetime import datetime, timedelta, timezone

    from . import chartimg

    tok, cid = notify.creds(target)
    if send_telegram and not (tok and cid):
        return [f"발송 대상 '{target}' 토큰/chat_id 미설정 — 중단"]

    alerts_cfg = _load(ALERTS_FILE, {})
    kst = datetime.now(timezone(timedelta(hours=9)))
    log: list[str] = []

    # --- 헤더 요약 ---
    head = [f"{title}  ({kst:%Y-%m-%d %H:%M} KST)", ""]
    metas = []
    for sym, mkt, name in symbols:
        df = prices.get_ohlcv(sym, mkt, "1y")   # 매수구간 추세 필터(200일선)에 필요
        if df is None or df.empty:
            head.append(f"• {name}({sym})  데이터 없음")
            metas.append((sym, mkt, name, None, None))
            continue
        lq = prices.get_live_quote(sym, mkt)
        cur = lq.get("price") or float(df["close"].iloc[-1])
        prev = lq.get("prev_close") or (float(df["close"].iloc[-2]) if len(df) >= 2 else cur)
        chg = (cur - prev) / prev * 100 if prev else 0.0
        up = signals.evaluate(df).get("up_pct")
        _, band = band_of(up)
        arrow = _arrow(chg)
        up_s = f"{up:.0f}({band})" if up is not None else "-"
        head.append(f"• {name}({sym})  {_fmt_price(cur, mkt)} {arrow}{chg:+.1f}%  · 신호 {up_s}")
        metas.append((sym, mkt, name, (cur, chg, up), df))
    head += ["", "※ 보조 지표 요약 · 투자 판단은 본인 책임"]
    if send_telegram:
        notify.send("\n".join(head), chat_id=cid, token=tok)
    log.append("헤더 발송")

    # --- 종목별 차트 + 캡션 ---
    for sym, mkt, name, meta, df in metas:
        if meta is None:
            continue
        cur, chg, up = meta
        cfg = alerts_cfg.get(_key(sym, mkt), {})
        oe, ol = _opinion(up)
        up_s = f"{up:.0f}" if up is not None else "-"
        arrow = _arrow(chg)
        lines = [
            f"{oe} {ol} ({up_s}/100)",
            f"{_html.escape(name)} ({sym})  {arrow}{chg:+.1f}%",
            _DIV, "💰 가격 요약",
            *_price_rows(mkt, df, cfg, cur=cur),
        ]
        # 매수 관심구간 — 자동 산출(추세·근거 부족하면 사유를 그대로 적는다)
        zone = entry_mod.compute_entry_zone(df, cur)
        lines.append(_DIV)
        if zone.get("ok"):
            lines += entry_mod.format_zone(zone, lambda v: _fmt_price(v, mkt))
        else:
            lines.append(f"🟢 매수 관심구간 — {_html.escape(zone.get('reason', '없음'))}")
        news = _news_multi(name, mkt, limit=news_n)
        base_cap = "\n".join(lines)
        full_cap = "\n".join(lines + ([_DIV] + news if news else []))
        if not send_telegram:
            log.append(f"{name}: (미발송) 캡션 {len(full_cap)}자")
            continue
        path = None
        try:
            fd, path = tempfile.mkstemp(suffix=".png", prefix="cbrief_")
            os.close(fd)
            out = chartimg.render_chart(sym, mkt, name, path,
                                        target=cfg.get("target"), entry=cfg.get("entry"), df=df)
            if out and len(full_cap) <= 1024:
                notify.send_photo(out, caption=full_cap, parse_mode="HTML",
                                  chat_id=cid, token=tok)
                log.append(f"{name}: 차트+뉴스 인라인")
            elif out:
                notify.send_photo(out, caption=base_cap, parse_mode="HTML",
                                  chat_id=cid, token=tok)
                if news:
                    notify.send("\n".join([f"📰 {_html.escape(name)} 관련 뉴스", ""] + news),
                                parse_mode="HTML", chat_id=cid, token=tok)
                log.append(f"{name}: 차트 + 뉴스 별도")
            else:
                notify.send(full_cap, parse_mode="HTML", chat_id=cid, token=tok)
                log.append(f"{name}: 텍스트 폴백")
        finally:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
    return log


def group_symbols() -> list[tuple[str, str, str]]:
    """단톡방 전용 종목 목록 → [(symbol, market, name), ...]"""
    return [
        (str(i["symbol"]), str(i["market"]).upper(), i.get("name", i["symbol"]))
        for i in _load(GROUP_WATCHLIST_FILE, [])
        if i.get("symbol") and i.get("market")
    ]


def build_group_briefing(send_telegram: bool = True, news_n: int = 3,
                         title: str = "📊 단톡방 브리핑") -> list[str]:
    """단톡방 종목 전체를 차트 + 가격요약 + 매수구간 + 뉴스로 발송."""
    syms = group_symbols()
    if not syms:
        return ["data/watchlist_group.json 이 비어 있음"]
    return build_chart_briefing(syms, send_telegram=send_telegram, news_n=news_n,
                                target="group", title=title)


def add_group_watch(query: str, market: str | None = None, name: str | None = None) -> dict:
    """단톡방 종목 목록에 추가 (개인 워치리스트와 별개)."""
    from . import search as search_mod
    cands = search_mod.search_symbols(query, limit=8)
    if market:
        mk = market.strip().upper()
        cands = [c for c in cands if c["market"] == mk] or cands
    if not cands:
        return {"ok": False, "msg": f"'{query}' 검색 결과 없음", "candidates": []}
    pick = cands[0]
    item = {"name": name or pick["name"], "symbol": pick["symbol"], "market": pick["market"]}
    wl = _load(GROUP_WATCHLIST_FILE, [])
    for w in wl:
        if str(w.get("symbol")) == item["symbol"] and str(w.get("market")).upper() == item["market"]:
            return {"ok": False, "msg": f"이미 있음: {w.get('name')}", "candidates": cands}
    wl.append(item)
    _save(GROUP_WATCHLIST_FILE, wl)
    return {"ok": True, "msg": f"단톡방 목록 추가: {item['name']} ({item['symbol']}/{item['market']})",
            "candidates": cands}


def check_market_halt(send_telegram: bool = True,
                      window_min: int = 30, cooldown_min: int = 40) -> list[str]:
    """코스피/코스닥 사이드카·서킷브레이커 '발동'을 뉴스 속보로 감지해 즉시 알림.

    공식 실시간 무료 API가 없어 뉴스(Google News RSS) 기반으로 감지한다.
    - window_min: 이 시간(분) 내 발행된 기사만 '방금 발동'으로 인정(과거 설명기사 배제)
    - cooldown_min: 같은 유형은 이 시간(분) 안에 재알림하지 않음(속보 도배 방지)
    반환: 발송한 메시지 목록.
    """
    import time

    from . import news as news_mod

    state = _load(HALT_STATE_FILE, {})
    last: dict = state.get("last", {})
    now = time.time()
    triggers = [
        ("사이드카", "🟧 사이드카 발동"),
        ("서킷브레이커", "🟥 서킷브레이커(CB) 발동"),
    ]
    msgs: list[str] = []
    for kw, label in triggers:
        # 최근 알림했으면 스킵 (같은 이벤트 도배 방지)
        if last.get(kw) and now - float(last[kw]) < cooldown_min * 60:
            continue
        try:
            items = news_mod.get_news(f"{kw} 발동", region="KR", limit=10)
        except Exception:
            continue
        fresh = None
        for it in items:
            title = it.get("title", "")
            ts = it.get("ts")
            if kw not in title or "발동" not in title:
                continue
            if ts is None or (now - float(ts)) > window_min * 60:
                continue  # 발행시각 불명 또는 오래된 기사 → 제외
            fresh = it
            break  # RSS는 최신순 → 첫 유효 기사 사용
        if fresh:
            text = f"⚠️ {label}\n📰 {fresh['title']}"
            if fresh.get("link"):
                text += f"\n{fresh['link']}"
            msgs.append(text)
            if send_telegram:
                notify.send(text)
            last[kw] = now
    state["last"] = last
    _save(HALT_STATE_FILE, state)
    return msgs


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

    arw = _arrow

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
