"""
주식·자산 관리 + 기술적 분석 대시보드
실행:  streamlit run app.py
"""
from __future__ import annotations

import html as html_lib
import json
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src import alerts as alert_engine
from src import backtest as bt_mod
from src import gitstore
from src import glossary
from src import indicators as ind
from src import levels as lv_mod
from src import levels_touch as lt_mod
from src import market as market_mod
from src import news as news_mod
from src import notify
from src import prices, search, signals
from src import summary as summary_mod

# ---------------------------------------------------------------------------
# 기본 설정 / 경로
# ---------------------------------------------------------------------------
st.set_page_config(page_title="내 주식·자산 대시보드", page_icon="📈", layout="wide",
                   initial_sidebar_state="expanded")

DATA_DIR = Path(__file__).parent / "data"
PORTFOLIO_FILE = DATA_DIR / "portfolio.json"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"

MARKET_LABELS = {"KR": "🇰🇷 한국주식", "US": "🇺🇸 미국주식", "COIN": "🪙 코인"}
PERIOD_OPTIONS = {"6개월": "6mo", "1년": "1y", "2년": "2y", "5년": "5y"}

# 금융 대시보드 CSS (Pretendard · 카드 · 배지 · 점수바 · 차분한 톤)
CUSTOM_CSS = """
<style>
@import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.css");
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"] {
    font-family: "Pretendard Variable", Pretendard, Inter, -apple-system, system-ui, "Segoe UI", Roboto, sans-serif;
}
[data-testid="stAppViewContainer"] { background: #F6F8FB; }
.block-container { padding-top: 2rem; max-width: 1180px; }

/* 헤딩 — 차분, 너무 크지 않게 */
h1 { font-size: 26px !important; font-weight: 700; color: #111827; letter-spacing: -0.02em; }
h2 { font-size: 20px !important; font-weight: 700; color: #111827; letter-spacing: -0.01em; }
h3 { font-size: 18px !important; font-weight: 700; color: #111827; }

a, a:visited { color: #2563EB !important; text-decoration: none; }
a:hover { text-decoration: underline; }

/* 버튼 */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
    border-radius: 10px !important; font-weight: 600; border: 1px solid #E5E7EB;
    transition: all .12s ease;
}
.stButton > button[kind="primary"] { background: #2563EB; border-color: #2563EB; color: #fff; }
.stButton > button[kind="primary"]:hover { background: #1d4ed8; border-color: #1d4ed8; }

[data-testid="stMetricLabel"] p { color: #6B7280; font-weight: 600; font-size: 13px; }
[data-testid="stMetricValue"] { font-weight: 700; letter-spacing: -0.01em; color: #111827; }

.stTextInput input, .stNumberInput input { border-radius: 10px !important; }
[data-baseweb="select"] > div { border-radius: 10px !important; }

[data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid #E5E7EB; }

[data-testid="stExpander"] { border-radius: 14px; border: 1px solid #E5E7EB; overflow: hidden; background:#fff; }
[data-testid="stExpander"] summary { font-weight: 600; }
[data-testid="stDataFrame"] { border-radius: 10px; }
hr { border-color: #E5E7EB; margin: 1rem 0; }

/* 요약/지표 카드 */
.card {
    background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 14px;
    padding: 16px 18px; box-shadow: 0 1px 2px rgba(16,24,40,0.04); height: 100%;
}
.card .lbl { color: #6B7280; font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.card .val { font-size: 28px; font-weight: 700; letter-spacing: -0.02em; color: #111827; line-height: 1.1; }
.card .val.sm { font-size: 22px; }
.card .sub { font-size: 13px; color: #6B7280; margin-top: 6px; }
.up { color: #E53935; } .down { color: #2563EB; } .neutral { color: #9CA3AF; }

/* 배지 */
.badge {
    display: inline-block; padding: 3px 10px; border-radius: 999px;
    font-size: 12px; font-weight: 600; margin: 2px 4px 2px 0; border: 1px solid transparent;
}
.badge.up { background: #FDECEA; color: #C62828; }
.badge.down { background: #E8EEFD; color: #1d4ed8; }
.badge.warn { background: #FEF3E2; color: #B45309; }
.badge.calm { background: #F3F4F6; color: #6B7280; }

/* 종합 점수 바 */
.scorebar-track { background: #EEF1F5; border-radius: 999px; height: 10px; width: 100%; overflow: hidden; }
.scorebar-fill { height: 100%; border-radius: 999px; }

/* 총평 박스 */
.summary-box {
    background: #FFFFFF; border: 1px solid #E5E7EB; border-left: 4px solid #2563EB;
    border-radius: 12px; padding: 18px 22px; line-height: 1.7; font-size: 15px; color: #111827;
}

/* 표가 좁은 화면을 넘칠 때 가로 스크롤 (셀 겹침 방지) */
.table-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }

/* ── 모바일 반응형 (≤640px) ─────────────────────────────
   좁은 화면에서 st.columns가 옆으로 찌그러져 글자/숫자가 세로로 깨지는 걸 방지.
   컬럼을 세로로 쌓고, 카드 값은 줄바꿈 금지, 표는 가로 스크롤. */
@media (max-width: 640px) {
    .block-container { padding-left: .6rem; padding-right: .6rem; padding-top: 1rem; max-width: 100%; }
    [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; gap: .5rem !important; }
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
    [data-testid="stHorizontalBlock"] > [data-testid="column"] {
        flex: 1 1 100% !important; width: 100% !important; min-width: 100% !important;
    }
    .card { padding: 13px 14px; }
    .card .val { font-size: 22px; white-space: nowrap; }
    .card .val.sm { font-size: 19px; white-space: nowrap; }
    [data-testid="stMetricValue"] { font-size: 22px !important; white-space: nowrap; }
    table.sig { font-size: .82rem; }
    table.sig th, table.sig td { padding: 7px 8px !important; }
    h1 { font-size: 22px !important; } h2 { font-size: 18px !important; }
}

/* 접힌 사이드바 '메뉴 열기' 버튼 — 모바일에서 잘 보이게 파란 버튼으로 */
[data-testid="collapsedControl"], [data-testid="stSidebarCollapsedControl"] {
    background: #2563EB !important; border-radius: 10px !important;
    padding: 5px 7px !important; box-shadow: 0 2px 8px rgba(37,99,235,.4);
    top: .55rem !important; left: .55rem !important;
}
[data-testid="collapsedControl"] svg, [data-testid="stSidebarCollapsedControl"] svg {
    color: #fff !important; fill: #fff !important; width: 1.7rem !important; height: 1.7rem !important;
}
</style>
"""


# ---------------------------------------------------------------------------
# 저장/로드
# ---------------------------------------------------------------------------
def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def bridge_secrets_to_env() -> None:
    """Streamlit secrets의 텔레그램 토큰을 환경변수로 노출 → notify가 클라우드에서도 인식.
    (notify.resolve_token()이 os.environ을 1순위로 읽음)"""
    try:
        for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
            v = st.secrets.get(k)
            if v and not os.environ.get(k):
                os.environ[k] = str(v)
    except Exception:
        pass


def gh_config() -> tuple[str | None, str]:
    """Streamlit secrets에서 GitHub 저장 설정 읽기. (토큰, repo). 없으면 (None, repo기본)."""
    try:
        token = st.secrets.get("GH_TOKEN")
        repo = st.secrets.get("GH_REPO", "kimdike/jusik")
        return (token or None), repo
    except Exception:
        return None, "kimdike/jusik"


def save_json_cloud(rel_path: str, data, message: str) -> tuple[bool, str]:
    """클라우드(secrets에 GH_TOKEN 있을 때)면 GitHub 저장소에도 커밋해 영구화."""
    token, repo = gh_config()
    if not token:
        return False, "no-token"
    content = json.dumps(data, ensure_ascii=False, indent=2)
    return gitstore.save_file(repo, rel_path, content, message, token)


def alert_tick(price: float | None, market: str) -> float:
    """목표가/손절가 ▲▼ 스텝 단위 (가격 규모·시장에 맞게)."""
    p = price or 0
    if market.upper() == "US":
        return round(max(0.01, p * 0.005), 2) or 0.5
    if p >= 1_000_000:
        return 10000.0
    if p >= 100_000:
        return 1000.0
    if p >= 10_000:
        return 100.0
    if p >= 1_000:
        return 10.0
    return 1.0


def set_price_pct(state_key: str, base: float | None, pct: float, market: str) -> None:
    """버튼 콜백: 현재가(base) 대비 pct% 값을 위젯 상태에 채움. (위젯 생성 전 실행돼 안전)"""
    if base is None:
        return
    val = base * (1 + pct / 100.0)
    st.session_state[state_key] = round(val, 2) if market.upper() == "US" else float(round(val))


# ---------------------------------------------------------------------------
# 데이터 (캐시)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def fetch_ohlcv(symbol: str, market: str, period: str, timeframe: str = "D") -> pd.DataFrame:
    return prices.get_ohlcv(symbol, market, period, timeframe=timeframe)


@st.cache_data(ttl=120, show_spinner=False)
def fetch_price(symbol: str, market: str):
    return prices.get_current_price(symbol, market)


@st.cache_data(ttl=600, show_spinner=False)
def fetch_fx() -> float:
    return prices.get_fx_usdkrw() or 1380.0


@st.cache_data(ttl=300, show_spinner=False)
def fetch_search(query: str) -> list:
    return search.search_symbols(query, limit=12)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_quote(symbol: str, market: str) -> dict:
    return prices.get_quote(symbol, market)


def search_labels(results: list, top: int = 10):
    """검색 결과에 거래대금·시총을 붙여 라벨 생성 + 거래대금 큰 순 정렬."""
    enriched = []
    for r in results[:top]:
        enriched.append({**r, **fetch_quote(r["symbol"], r["market"])})
    enriched.sort(key=lambda x: x.get("value_24h") or 0, reverse=True)
    labels = []
    for r in enriched:
        extra = []
        if r.get("value_24h"):
            extra.append(f"거래대금 {fmt_marketcap(r['value_24h'], r['market'])}")
        if r.get("market_cap"):
            extra.append(f"시총 {fmt_marketcap(r['market_cap'], r['market'])}")
        tail = ("  ·  " + " · ".join(extra)) if extra else ""
        labels.append(f"{r['name']} · {r['symbol']} ({r['extra']}){tail}")
    return labels, enriched


@st.cache_data(ttl=600, show_spinner=False)
def fetch_fundamentals(symbol: str, market: str) -> dict:
    return prices.get_fundamentals(symbol, market)


@st.cache_data(ttl=600, show_spinner=False)
def fetch_news(query: str, region: str) -> list:
    return news_mod.get_news(query, region=region, limit=8)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_indices() -> list:
    return market_mod.get_indices()


@st.cache_data(ttl=600, show_spinner=False)
def fetch_fear_greed() -> dict | None:
    return market_mod.get_fear_greed_crypto()


@st.cache_data(ttl=600, show_spinner=False)
def run_backtest_cached(symbol: str, market: str, period: str,
                        buy_th: float, sell_th: float, fee_pct: float) -> dict:
    """OHLCV 페치 + 백테스트. 무겁기 때문에 결과를 캐시한다(봉 수에 따라 평가간격 자동 조절)."""
    df = prices.get_ohlcv(symbol, market, period)
    if df is None or df.empty:
        return {"ok": False, "reason": "데이터를 불러오지 못했어요. 심볼/시장/기간을 확인해 주세요."}
    n = len(df)
    step = max(1, n // 500)  # 봉이 많으면 신호 평가 간격을 늘려 속도 확보
    warmup = 130 if n > 170 else max(60, n // 3)
    return bt_mod.run_backtest(df, buy_th=buy_th, sell_th=sell_th,
                               warmup=warmup, fee_pct=fee_pct, step=step)


@st.cache_data(ttl=600, show_spinner=False)
def run_dip_backtest_cached(symbol: str, market: str, period: str,
                            dip_pct: float, take_pct: float, stop_pct: float) -> dict:
    """눌림목(매수자리) 전략 백테스트 — OHLCV 페치 후 실행, 결과 캐시."""
    df = prices.get_ohlcv(symbol, market, period)
    if df is None or df.empty:
        return {"ok": False, "reason": "데이터를 불러오지 못했어요. 심볼/시장/기간을 확인해 주세요."}
    return bt_mod.run_dip_backtest(df, dip_pct=dip_pct, take_pct=take_pct, stop_pct=stop_pct)


def render_news(items: list, empty_msg: str) -> None:
    """뉴스 목록 안전 렌더링 (외부 제목/링크 이스케이프 + 링크 스킴 검증)."""
    if not items:
        st.caption(empty_msg)
        return
    for n in items:
        title = html_lib.escape(n.get("title") or "")
        link = n.get("link") or ""
        if not link.startswith(("http://", "https://")):
            link = "#"
        meta = html_lib.escape(" · ".join(x for x in [n.get("source"), n.get("published")] if x))
        st.markdown(
            f"- [{title}]({link})  \n  <span style='color:#888;font-size:0.85em'>{meta}</span>",
            unsafe_allow_html=True,
        )


def card_html(label: str, value: str, sub: str = "", value_cls: str = "", val_sm: bool = False) -> str:
    sub_html = f'<div class="sub">{sub}</div>' if sub else ""
    sm = " sm" if val_sm else ""
    return (f'<div class="card"><div class="lbl">{label}</div>'
            f'<div class="val{sm} {value_cls}">{value}</div>{sub_html}</div>')


def _chg_cls(v) -> str:
    if v is None:
        return "neutral"
    return "up" if v > 0 else ("down" if v < 0 else "neutral")


def risk_badges(result: dict, all_ind: dict, levels: dict) -> list[tuple[str, str]]:
    """리스크 배지 [(라벨, 종류)]. 종류: warn / calm."""
    out = []
    rsi_s = all_ind.get("rsi")
    rv = float(rsi_s.dropna().iloc[-1]) if rsi_s is not None and not rsi_s.dropna().empty else None
    if rv is not None and rv >= 70:
        out.append(("과열 주의 · RSI 높음", "warn"))
    elif rv is not None and rv <= 30:
        out.append(("과매도 구간", "warn"))
    res = levels.get("resistances") or []
    sup = levels.get("supports") or []
    if res and abs(res[0]["dist_pct"]) <= 3:
        out.append(("저항선 근접", "warn"))
    if sup and abs(sup[0]["dist_pct"]) <= 3:
        out.append(("지지선 근접", "warn"))
    up = result.get("up_pct")
    if up is not None and up < 45:
        out.append(("추세 약화", "warn"))
    if not out:
        out.append(("특이 위험 신호 없음", "calm"))
    return out


def indicator_mini_cards(result: dict, all_ind: dict) -> list[dict]:
    """차트 아래 지표 요약 카드용 데이터."""
    vd = {v["name"]: v for v in result.get("votes", [])}
    cls_map = {"bull": "up", "bear": "down", "neutral": "neutral"}
    out = []
    rsi_s = all_ind.get("rsi")
    rv = float(rsi_s.dropna().iloc[-1]) if rsi_s is not None and not rsi_s.dropna().empty else None
    for name, big in [
        ("RSI", f"{rv:.0f}" if rv is not None else "-"),
        ("MACD", None), ("이동평균 배열", None), ("볼린저밴드", None),
    ]:
        v = vd.get(name)
        if not v:
            continue
        lvl, _ = level_disp(v["signal"], v.get("strength", 1))
        out.append({
            "name": "이동평균" if name == "이동평균 배열" else name,
            "value": big if big is not None else lvl.split(" ")[-1],
            "cls": cls_map.get(v["signal"], "neutral"),
            "sub": v["detail"],
        })
    return out


def fmt_marketcap(v, market: str) -> str:
    """시가총액 사람이 읽기 좋게."""
    if not v:
        return "-"
    if market == "US":
        if v >= 1e12:
            return f"${v/1e12:.2f}조달러"
        return f"${v/1e9:.1f}B"
    # KRW
    if v >= 1e12:
        return f"{v/1e12:.1f}조원"
    return f"{v/1e8:.0f}억원"


def fmt_krw(v) -> str:
    if v is None:
        return "-"
    return f"{v:,.0f}원"


def fmt_native(v, market: str) -> str:
    if v is None:
        return "-"
    return f"${v:,.2f}" if market == "US" else f"{v:,.0f}원"


# 방향+세기 -> (라벨, 색상). 한국식 색: 상승=빨강, 하락=파랑
LEVELS = {
    ("bull", 2): ("▲▲ 강한 상승", "#c0392b"),
    ("bull", 1): ("▲ 상승", "#e74c3c"),
    ("neutral", 1): ("■ 중립", "#95a5a6"),
    ("bear", 1): ("▼ 하락", "#2980b9"),
    ("bear", 2): ("▼▼ 강한 하락", "#16527a"),
}


def level_disp(signal: str, strength: int):
    if signal == "neutral":
        return LEVELS[("neutral", 1)]
    return LEVELS[(signal, 2 if strength >= 2 else 1)]


# ---------------------------------------------------------------------------
# 차트
# ---------------------------------------------------------------------------
# 차트 조작 설정: 마우스 휠 줌, 더블클릭 원상복구, 깔끔한 툴바
CHART_CONFIG = {
    "scrollZoom": True,
    "responsive": True,          # 화면 크기에 맞춰 차트 자동 리사이즈 (모바일 대응)
    "displaylogo": False,
    "doubleClick": "reset",
    "modeBarButtonsToRemove": ["select2d", "lasso2d"],
    "toImageButtonOptions": {"format": "png", "filename": "chart", "scale": 2},
}


def make_chart(df: pd.DataFrame, all_ind: dict, title: str, levels: dict | None = None,
               channel: dict | None = None, touch: dict | None = None,
               long_ma: tuple | None = None) -> go.Figure:
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.6, 0.2, 0.2],
        subplot_titles=(title, "RSI", "MACD"),
    )

    # --- 가격 캔들 ---
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["open"], high=df["high"], low=df["low"], close=df["close"],
            name="가격",
            increasing_line_color="#e74c3c", decreasing_line_color="#3498db",
        ),
        row=1, col=1,
    )
    # 이동평균
    for key, color in [("sma20", "#f39c12"), ("sma60", "#16a085"), ("sma120", "#8e44ad")]:
        fig.add_trace(
            go.Scatter(x=df.index, y=all_ind[key], name=key.upper(),
                       line=dict(width=1, color=color)),
            row=1, col=1,
        )
    # 장기 이평선 (예: 200주선) — 두꺼운 빨강
    if long_ma is not None:
        _ma_s, _ma_lbl = long_ma
        fig.add_trace(
            go.Scatter(x=df.index, y=_ma_s, name=_ma_lbl,
                       line=dict(width=2.2, color="#d63031")),
            row=1, col=1,
        )

    # 일목균형표 구름대
    ichi = all_ind["ichimoku"]
    fig.add_trace(
        go.Scatter(x=df.index, y=ichi["senkou_a"], name="선행A", showlegend=False,
                   line=dict(width=0.5, color="rgba(46,204,113,0.5)")),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(x=df.index, y=ichi["senkou_b"], name="선행B", fill="tonexty",
                   fillcolor="rgba(46,204,113,0.12)", showlegend=False,
                   line=dict(width=0.5, color="rgba(231,76,60,0.5)")),
        row=1, col=1,
    )

    # --- RSI ---
    fig.add_trace(
        go.Scatter(x=df.index, y=all_ind["rsi"], name="RSI", showlegend=False,
                   line=dict(color="#9b59b6")),
        row=2, col=1,
    )
    fig.add_hline(y=70, line_dash="dot", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="blue", row=2, col=1)

    # --- MACD ---
    macd_df = all_ind["macd"]
    colors = ["#e74c3c" if v >= 0 else "#3498db" for v in macd_df["hist"].fillna(0)]
    fig.add_trace(go.Bar(x=df.index, y=macd_df["hist"], name="히스토그램", showlegend=False,
                         marker_color=colors), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=macd_df["macd"], name="MACD", showlegend=False,
                             line=dict(color="#2c3e50")), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=macd_df["signal"], name="시그널", showlegend=False,
                             line=dict(color="#e67e22")), row=3, col=1)

    # 평행 채널 (로그 회귀) — 큰 그림 추세
    if channel:
        fig.add_trace(go.Scatter(x=df.index, y=channel["upper"], name="채널 상단", showlegend=False,
                                 line=dict(width=1, color="rgba(231,76,60,0.65)")), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=channel["mid"], name="채널 중심", showlegend=False,
                                 line=dict(width=0.8, color="rgba(37,99,235,0.55)", dash="dash")), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=channel["lower"], name="채널 하단", showlegend=False,
                                 line=dict(width=1, color="rgba(22,160,133,0.65)")), row=1, col=1)

    # 지지/저항 — 터치 기반(실제 반응 자리) 우선, 없으면 기존 지표 기반 levels
    if touch and (touch.get("resistances") or touch.get("supports")):
        cur_px = float(df["close"].iloc[-1]) or 1.0
        res2 = (touch.get("resistances") or [])[:2]
        sup2 = (touch.get("supports") or [])[:2]
        sr = ([("저항", r, "rgba(192,57,43,0.7)", "#c0392b") for r in res2]
              + [("지지", s, "rgba(22,160,133,0.85)", "#16a085") for s in sup2])
        sr.sort(key=lambda t: t[1]["price"], reverse=True)
        last_lbl_y = None  # 라벨이 서로 겹치지 않게: 직전 라벨과 4.5% 이상 떨어질 때만 라벨 표시
        for tag, lv, line_col, dot_col in sr:
            show = last_lbl_y is None or abs(lv["price"] - last_lbl_y) / cur_px > 0.045
            fig.add_hline(
                y=lv["price"], line_dash="dash", line_color=line_col, row=1, col=1,
                annotation_text=(f"{tag} {lv['price']:,.0f}·{lv['touches']}회" if show else ""),
                annotation_position="right", annotation_font_size=10,
            )
            if show:
                last_lbl_y = lv["price"]
            # 실제 반응한 지점(피벗)을 점으로 — 눈에 보이는 근거
            xs = [df.index[p] for p in lv.get("members", []) if 0 <= p < len(df)]
            if xs:
                fig.add_trace(go.Scatter(x=xs, y=[lv["price"]] * len(xs), mode="markers",
                                         showlegend=False,
                                         marker=dict(size=6, color=dot_col,
                                                     line=dict(width=1, color="white"))),
                              row=1, col=1)
    elif levels:
        for s in levels.get("resistances", [])[:2]:
            fig.add_hline(y=s["price"], line_dash="dash", line_color="rgba(192,57,43,0.6)",
                          annotation_text=f"저항 {s['price']:,.0f}", annotation_position="right",
                          row=1, col=1)
        for s in levels.get("supports", [])[:2]:
            fig.add_hline(y=s["price"], line_dash="dash", line_color="rgba(41,128,185,0.6)",
                          annotation_text=f"지지 {s['price']:,.0f}", annotation_position="right",
                          row=1, col=1)

    fig.update_layout(
        height=640, xaxis_rangeslider_visible=False, hovermode="x unified",
        dragmode="pan",  # 모바일에서 한 손가락 이동 + 핀치 확대가 자연스럽게
        # 범례는 아래로 — 좁은 화면에서 상단 기간버튼·제목과 겹치지 않게
        legend=dict(orientation="h", yanchor="top", y=-0.06, xanchor="left", x=0,
                    font=dict(size=10)),
        margin=dict(l=8, r=96, t=58, b=44),  # 오른쪽 지지/저항 라벨 여백(잘림 방지) + 하단 범례
    )
    # 빠른 기간 버튼 (가격 차트 위) — 탭하면 그 구간으로 확대
    fig.update_xaxes(
        rangeselector=dict(
            buttons=[
                dict(count=1, label="1개월", step="month", stepmode="backward"),
                dict(count=3, label="3개월", step="month", stepmode="backward"),
                dict(count=6, label="6개월", step="month", stepmode="backward"),
                dict(count=1, label="1년", step="year", stepmode="backward"),
                dict(step="all", label="전체"),
            ],
            x=0, y=1.05, font=dict(size=10), bgcolor="rgba(255,255,255,0.85)",
        ),
        row=1, col=1,
    )
    # 모든 y축 자동범위 (더블클릭 시 원상복구가 자연스럽게)
    fig.update_yaxes(autorange=True, fixedrange=False)
    return fig


def gauge(up_pct: float) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=up_pct,
            number={"suffix": "%", "font": {"size": 40}},
            title={"text": "상승 우세 신호"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#2c3e50"},
                "steps": [
                    {"range": [0, 30], "color": "#3498db"},
                    {"range": [30, 45], "color": "#aed6f1"},
                    {"range": [45, 55], "color": "#f7f9f9"},
                    {"range": [55, 70], "color": "#f5b7b1"},
                    {"range": [70, 100], "color": "#e74c3c"},
                ],
            },
        )
    )
    fig.update_layout(height=260, margin=dict(l=20, r=20, t=40, b=10))
    return fig


# ---------------------------------------------------------------------------
# 페이지: 포트폴리오
# ---------------------------------------------------------------------------
def page_portfolio():
    st.title("내 자산")
    st.caption("보유 종목·수량·매입가를 입력하면 현재가 기준 평가액과 수익률을 계산합니다. "
               "미국 주식은 원화로 환산됩니다.")

    portfolio = load_json(PORTFOLIO_FILE, [])
    df_edit = pd.DataFrame(portfolio) if portfolio else pd.DataFrame(
        columns=["name", "symbol", "market", "qty", "avg_price"]
    )

    edited = st.data_editor(
        df_edit,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "name": st.column_config.TextColumn("이름"),
            "symbol": st.column_config.TextColumn("심볼", help="한국:6자리코드(005930) / 미국:티커(AAPL) / 코인:BTC"),
            "market": st.column_config.SelectboxColumn("시장", options=["KR", "US", "COIN"]),
            "qty": st.column_config.NumberColumn("수량", format="%.4f"),
            "avg_price": st.column_config.NumberColumn("평균매입가", help="해당 시장 통화 기준 (미국=USD, 그 외=원)"),
        },
        key="portfolio_editor",
    )

    if st.button("💾 포트폴리오 저장", type="primary"):
        save_json(PORTFOLIO_FILE, edited.fillna("").to_dict("records"))
        st.success("저장 완료!")

    if edited.empty:
        st.info("종목을 추가해 주세요.")
        return

    fx = fetch_fx()
    rows, total_value, total_cost = [], 0.0, 0.0
    with st.spinner("현재가 불러오는 중..."):
        for _, r in edited.iterrows():
            sym, mkt = str(r.get("symbol", "")).strip(), str(r.get("market", "")).strip().upper()
            if not sym or mkt not in MARKET_LABELS:
                continue
            try:
                qty = float(r.get("qty") or 0)
                avg = float(r.get("avg_price") or 0)
            except (TypeError, ValueError):
                continue
            cur = fetch_price(sym, mkt)
            rate = fx if mkt == "US" else 1.0
            value_krw = (cur or 0) * qty * rate
            cost_krw = avg * qty * rate
            profit = value_krw - cost_krw
            pct = (profit / cost_krw * 100) if cost_krw else 0.0
            total_value += value_krw
            total_cost += cost_krw
            rows.append({
                "이름": r.get("name", sym),
                "시장": MARKET_LABELS.get(mkt, mkt),
                "현재가": fmt_native(cur, mkt),
                "수량": qty,
                "평가액(원)": value_krw,
                "수익(원)": profit,
                "수익률": f"{pct:+.1f}%",
            })

    total_profit = total_value - total_cost
    total_pct = (total_profit / total_cost * 100) if total_cost else 0.0

    c1, c2, c3 = st.columns(3)
    c1.metric("총 평가액", fmt_krw(total_value))
    c2.metric("총 매입액", fmt_krw(total_cost))
    c3.metric("총 손익", fmt_krw(total_profit), f"{total_pct:+.1f}%")

    if rows:
        res = pd.DataFrame(rows)
        st.dataframe(
            res.style.format({"평가액(원)": "{:,.0f}", "수익(원)": "{:,.0f}", "수량": "{:.4f}"}),
            use_container_width=True,
        )
        # 자산 비중 파이차트
        pie = go.Figure(go.Pie(labels=res["이름"], values=res["평가액(원)"], hole=0.4))
        pie.update_layout(title="자산 비중", height=360, margin=dict(t=40, b=10))
        st.plotly_chart(pie, use_container_width=True)
    st.caption(f"환율 적용: 1 USD = {fx:,.0f}원 · 데이터 5분 캐시")


# ---------------------------------------------------------------------------
# 페이지: 기술적 분석 (핵심)
# ---------------------------------------------------------------------------
def page_analysis():
    st.title("기술적 분석")
    st.caption("현재 지표 기반 모멘텀 요약 · 투자 판단을 돕는 참고 정보이며 수익을 보장하지 않습니다.")

    # 종목 선택 — 이름 검색 + 보유/관심 빠른선택
    pf = load_json(PORTFOLIO_FILE, [])
    wl = load_json(WATCHLIST_FILE, [])
    options = {}  # 표시키 -> (symbol, market, name)
    for item in pf + wl:
        nm = item.get("name", item["symbol"])
        key = f"{nm} ({item['symbol']}/{item['market']})"
        options[key] = (item["symbol"], item["market"], nm)

    symbol, market, dispname = "005930", "KR", "삼성전자"  # 기본값
    col1, col2 = st.columns(2)
    with col1:
        q = st.text_input("🔍 이름으로 검색", placeholder="예: 삼성전자 · 테슬라 · 비트코인",
                          help="한국주식=한글, 미국주식=영문 또는 한글(애플·테슬라), 코인=한글/영문")
        picked = None
        if q.strip():
            results = fetch_search(q.strip())
            if results:
                with st.spinner("종목 정보 불러오는 중..."):
                    labels, results = search_labels(results)
                sel = st.selectbox("검색 결과 (거래대금 큰 순)", labels, key="search_results")
                r = results[labels.index(sel)]
                picked = (r["symbol"], r["market"], r["name"])
            else:
                st.caption("결과 없음 — 철자나 한/영 표기를 바꿔보세요.")
    with col2:
        quick = st.selectbox("또는 보유·관심 종목", ["— 선택 안 함 —"] + list(options.keys()))

    if picked:
        symbol, market, dispname = picked
    elif quick != "— 선택 안 함 —":
        symbol, market, dispname = options[quick]

    tcol, pcol, ocol = st.columns([1.2, 2, 1.4])
    with tcol:
        tf_label = st.radio("봉", ["일봉", "주봉", "월봉"], index=0, horizontal=True,
                            help="일봉=단기 매매자리 / 주봉·월봉=큰 그림 추세·채널")
        timeframe = {"일봉": "D", "주봉": "W", "월봉": "M"}[tf_label]
    with pcol:
        if timeframe == "D":
            period_label = st.radio("기간", list(PERIOD_OPTIONS.keys()), index=1, horizontal=True)
            period = PERIOD_OPTIONS[period_label]
        else:
            period_label = tf_label
            period = "1y"  # 주/월봉은 내부에서 더 긴 기간 자동 사용
            st.caption("주봉/월봉은 자동으로 긴 기간을 씁니다.")
    with ocol:
        show_channel = st.checkbox("평행 채널", value=(timeframe != "D"),
                                   help="로그 회귀 기반 장기 추세 채널")

    df = fetch_ohlcv(symbol, market, period, timeframe)
    if df.empty:
        st.error(f"'{symbol}' ({market}) 데이터를 불러오지 못했어요. 심볼/시장을 확인해 주세요.")
        return
    # 월봉은 너무 긴 과거만 잘라 표시 안정화 (주봉은 200주선 계산 위해 전체 유지)
    if timeframe == "M":
        df = df.tail(240)

    all_ind = ind.compute_all(df)
    result = signals.evaluate(df)
    levels = lv_mod.compute_levels(df, all_ind)
    touch = lt_mod.touch_levels(df)
    channel = lt_mod.regression_channel(df) if show_channel else None
    # 장기 이평선 (일봉=200일선, 주봉=200주선) — 데이터 충분할 때만
    long_ma = None
    if timeframe in ("D", "W"):
        _s = ind.sma(df["close"], 200)
        if int(_s.notna().sum()) >= 10:
            long_ma = (_s, "200주선" if timeframe == "W" else "200일선")
    cur = float(df["close"].iloc[-1])
    fund = fetch_fundamentals(symbol, market) if market != "COIN" else {}

    # 등락률(전일 대비) · 기간 수익률
    prev = float(df["close"].iloc[-2]) if len(df) >= 2 else cur
    chg = (cur - prev) / prev * 100 if prev else 0.0
    first = float(df["close"].iloc[0]) if len(df) else cur
    pr = (cur - first) / first * 100 if first else 0.0
    mkt_label = {"KR": "KRX", "US": "US", "COIN": "Upbit"}.get(market, market)

    # 종목 헤더 (한 줄)
    st.markdown(
        f'<div style="font-size:15px;color:#6B7280;margin:.2rem 0 .5rem">'
        f'<b style="color:#111827;font-size:17px">{dispname}</b>'
        f'&nbsp; {symbol} · {mkt_label}</div>',
        unsafe_allow_html=True,
    )

    # ===== Hero: 현재가·등락률 + 종합 의견 + 종합점수/신뢰도 (결론 먼저) =====
    hv = summary_mod.hero_verdict(result, all_ind)
    up = result.get("up_pct")
    hcol = hv["color"]
    chg_col = "#16A34A" if chg > 0 else "#DC2626" if chg < 0 else "#6B7280"
    pr_col = "#16A34A" if pr > 0 else "#DC2626" if pr < 0 else "#6B7280"
    sc_str = str(hv["score"]) if hv["score"] is not None else "-"
    conf_str = f'{hv["confidence"]}%' if hv["confidence"] is not None else "-"
    bar_pct = hv["score"] if hv["score"] is not None else 50
    hleft, hright = st.columns([1, 1.25])
    with hleft:
        st.markdown(
            f'<div class="card"><div class="lbl">현재가</div>'
            f'<div style="font-size:30px;font-weight:800;letter-spacing:-.02em;color:#111827;line-height:1.1">'
            f'{fmt_native(cur, market)}</div>'
            f'<div style="font-size:16px;font-weight:700;color:{chg_col};margin-top:4px">{chg:+.2f}%'
            f'<span style="font-size:12px;color:#9CA3AF;font-weight:500"> 전일 대비</span></div>'
            f'<div class="sub">{tf_label} 수익률 <span style="color:{pr_col};font-weight:600">{pr:+.1f}%</span></div>'
            f'</div>', unsafe_allow_html=True)
    with hright:
        st.markdown(
            f'<div class="card" style="border-top:4px solid {hcol}">'
            f'<div class="lbl">종합 의견</div>'
            f'<div style="font-size:25px;font-weight:800;color:{hcol};margin:1px 0">{hv["emoji"]} {hv["action"]}</div>'
            f'<div class="sub" style="margin-bottom:7px">{hv["meaning"]}</div>'
            f'<div style="display:flex;gap:18px;align-items:baseline">'
            f'<div><span style="font-size:22px;font-weight:800;color:#111827">{sc_str}</span>'
            f'<span style="font-size:12px;color:#9CA3AF">/100 종합점수</span></div>'
            f'<div style="font-size:13px;color:#6B7280">신뢰도 <b style="color:#374151">{conf_str}</b></div></div>'
            f'<div class="scorebar-track" style="margin:8px 0 2px">'
            f'<div class="scorebar-fill" style="width:{bar_pct}%;background:{hcol}"></div></div>'
            f'</div>', unsafe_allow_html=True)

    # ===== 판단 근거 (✅상승 / ❌하락 / ➖중립) =====
    if hv["reasons"]:
        chips = ""
        for kind, txt in hv["reasons"]:
            c = "#16A34A" if kind == "bull" else "#DC2626" if kind == "bear" else "#6B7280"
            chips += (f'<span style="display:inline-block;background:#F3F4F6;border-radius:8px;'
                      f'padding:5px 11px;margin:3px 5px 3px 0;font-size:13.5px;color:{c};'
                      f'font-weight:600">{html_lib.escape(txt)}</span>')
        st.markdown(f'<div style="margin:12px 0 2px"><div class="lbl" style="margin-bottom:4px">'
                    f'판단 근거 (핵심 지표)</div>{chips}</div>', unsafe_allow_html=True)
        st.caption("✅상승 ❌하락 ➖중립 · 종합점수=상승 쏠림도(오를 확률 아님) · 신뢰도=쏠림·추세강도 기반 신호 강도")

    st.write("")
    # 메인 차트 (화면 중심) — 터치 기반 지지/저항 + (옵션) 평행 채널
    st.plotly_chart(make_chart(df, all_ind, f"{dispname} ({symbol}) · {tf_label}",
                               levels, channel=channel, touch=touch, long_ma=long_ma),
                    use_container_width=True, config=CHART_CONFIG)
    if channel:
        pos = channel["position"]
        loc = ("채널 상단(과열권)" if pos >= 80 else "채널 하단(저점권)" if pos <= 20
               else "채널 중단")
        st.caption(f"📐 평행 채널: 현재 **채널 내 위치 {pos:.0f}%** ({loc}) · {channel['trend']} 추세 "
                   f"· 빨강=상단(과열) 초록=하단(저점권). 채널 안에서 위치가 낮을수록 상대적 저평가.")
    st.caption("점(●)이 있는 지지/저항 = 과거 실제로 여러 번 반응한 자리(터치 횟수 표시)라 더 신뢰도가 높아요. "
               "차트: 더블클릭=원상복구 · 휠=확대 · 드래그=영역확대")

    # ===== 지지 / 저항 (세로 가격 사다리) =====
    st.subheader("지지 · 저항")
    res_lad = sorted(levels.get("resistances", []), key=lambda x: x["price"], reverse=True)[:3]
    sup_lad = sorted(levels.get("supports", []), key=lambda x: x["price"], reverse=True)[:3]

    def _lad_row(price, dist, kind):
        pal = {"res": ("#FDECEC", "#C0392B", "저항"),
               "cur": ("#EAF0FE", "#1D4ED8", "현재가"),
               "sup": ("#E8F5EE", "#16A34A", "지지")}
        bg, tc, tag = pal[kind]
        d = f'<span style="color:{tc};font-weight:700">{dist:+.1f}%</span>' if dist is not None else ""
        wt = "800" if kind == "cur" else "600"
        dot = "● " if kind == "cur" else ""
        return (f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'background:{bg};border-radius:8px;padding:9px 14px;margin:4px 0">'
                f'<span style="color:{tc};font-weight:{wt};font-size:14.5px">{dot}{tag} {fmt_native(price, market)}</span>'
                f'<span style="font-size:13px">{d}</span></div>')

    ladder = "".join(_lad_row(r["price"], r["dist_pct"], "res") for r in res_lad)
    ladder += _lad_row(cur, None, "cur")
    ladder += "".join(_lad_row(s["price"], s["dist_pct"], "sup") for s in sup_lad)
    st.markdown(ladder, unsafe_allow_html=True)
    st.caption("위=저항(돌파해야 더 오름/팔 자리), 아래=지지(받쳐주는 곳/살 자리). %는 현재가 대비 거리 · 참고용")

    # ===== 오늘 뉴스 (판단에 큰 영향 → 상단으로) =====
    st.subheader("오늘 뉴스")
    region = "US" if market == "US" else "KR"
    news_items = fetch_news(dispname, region)
    if news_items:
        ns = news_mod.summarize_news(news_items, exclude=dispname)
        chips = (f'<span class="badge up">긍정 {ns["pos"]}</span>'
                 f'<span class="badge calm">중립 {ns["neu"]}</span>'
                 f'<span class="badge down">부정 {ns["neg"]}</span>')
        kw = (" · ".join(ns["keywords"])) if ns["keywords"] else "추출된 키워드 없음"
        st.markdown(
            f'<div class="card"><div class="lbl">최근 뉴스 분위기 (제목 기반 추정)</div>'
            f'<div style="margin:8px 0 10px;line-height:2">{chips}</div>'
            f'<div class="sub"><b>주요 키워드</b> · {html_lib.escape(kw)}</div></div>',
            unsafe_allow_html=True)
        st.write("")
    render_news(news_items, "관련 뉴스를 찾지 못했어요.")

    # ===== 상세는 접이식(아코디언)으로 — 스크롤 축소 =====
    st.write("")
    st.markdown("##### 자세히 보기")

    with st.expander("📊 지표별 신호 (상세)"):
        # 지표 값 요약 (RSI 등) — 컴팩트
        mini = indicator_mini_cards(result, all_ind)
        if mini:
            mcols = st.columns(len(mini))
            for col, m in zip(mcols, mini):
                with col:
                    st.markdown(card_html(m["name"], m["value"], sub=m["sub"],
                                          value_cls=m["cls"], val_sm=True), unsafe_allow_html=True)
        pos_sig, neg_sig = summary_mod.signal_split(result)
        ps1, ps2 = st.columns(2)
        with ps1:
            items = "".join(f"<li>{html_lib.escape(s)}</li>" for s in pos_sig) or "<li style='color:#9CA3AF'>없음</li>"
            st.markdown(
                f'<div class="card" style="border-top:4px solid #16A34A">'
                f'<div class="lbl" style="color:#16A34A">긍정(상승) 신호 {len(pos_sig)}</div>'
                f'<ul style="margin:6px 0 0 -8px;font-size:14px;color:#374151;line-height:1.7">{items}</ul></div>',
                unsafe_allow_html=True)
        with ps2:
            items = "".join(f"<li>{html_lib.escape(s)}</li>" for s in neg_sig) or "<li style='color:#9CA3AF'>없음</li>"
            st.markdown(
                f'<div class="card" style="border-top:4px solid #DC2626">'
                f'<div class="lbl" style="color:#DC2626">부정(하락) 신호 {len(neg_sig)}</div>'
                f'<ul style="margin:6px 0 0 -8px;font-size:14px;color:#374151;line-height:1.7">{items}</ul></div>',
                unsafe_allow_html=True)
        rows_html = ""
        for v in result["votes"]:
            name, sig = v["name"], v["signal"]
            name_tip = html_lib.escape(glossary.explain(name), quote=True)
            why_tip = html_lib.escape(glossary.rationale(name, sig), quote=True)
            detail = html_lib.escape(v["detail"])
            label, color = level_disp(sig, v["strength"])
            stars, imp = summary_mod.weight_stars(v["weight"])
            rows_html += (
                "<tr>"
                f'<td title="{name_tip}"><b>{html_lib.escape(name)}</b><span class="info">ⓘ</span></td>'
                f'<td style="color:{color};font-weight:600;white-space:nowrap">{label}</td>'
                f'<td title="{why_tip}">{detail}<span class="info">ⓘ</span></td>'
                f'<td style="white-space:nowrap"><span style="color:#F59E0B">{stars}</span> '
                f'<span class="info">{imp}</span></td>'
                "</tr>"
            )
        st.markdown(
            f"""<style>
            table.sig {{ width:100%; border-collapse:collapse; font-size:0.9rem;
                         border:1px solid #E5E7EB; border-radius:12px; overflow:hidden; }}
            table.sig th, table.sig td {{ padding:9px 11px; border-bottom:1px solid #F1F3F5; text-align:left; }}
            table.sig th {{ background:#F9FAFB; font-weight:600; color:#6B7280; }}
            table.sig tr:last-child td {{ border-bottom:none; }}
            .info {{ color:#9CA3AF; font-size:0.8em; margin-left:4px; }}
            </style>
            <div class="table-scroll" style="margin-top:10px"><table class="sig">
            <tr><th>지표</th><th>신호</th><th>근거</th><th>중요도</th></tr>{rows_html}</table></div>""",
            unsafe_allow_html=True)

    with st.expander("🧾 종합 총평 (추세·모멘텀·리스크)"):
        st.markdown(
            f'<div class="summary-box">{summary_mod.build_summary(result, levels, all_ind, fund, market)}</div>',
            unsafe_allow_html=True)
        st.caption("기술적 지표를 자동 정리한 참고 해석입니다. 투자 판단과 책임은 본인에게 있습니다.")

    if market != "COIN" and fund:
        with st.expander("🏢 기업 지표 (PER·PBR·배당)"):
            f1, f2, f3, f4 = st.columns(4)
            per = fund.get("per"); pbr = fund.get("pbr")
            f1.metric("PER", f"{per:.1f}" if per is not None else "-")
            f2.metric("PBR", f"{pbr:.2f}" if pbr is not None else "-")
            f3.metric("시가총액", fmt_marketcap(fund.get("market_cap"), market))
            dy = fund.get("dividend_yield")
            f4.metric("배당수익률", f"{dy:.2f}%" if dy is not None else "-")
            fpos = fund.get("week52_pos")
            if fpos is not None:
                lo = fmt_native(fund.get("week52_low"), market)
                hi = fmt_native(fund.get("week52_high"), market)
                st.caption(f"52주 최저 {lo} ─ 현재 위치 {fpos*100:.0f}% ─ 최고 {hi}")
                st.progress(fpos)

    cv = summary_mod.consensus_view(fund, market)
    if cv:
        with st.expander("👔 전문가 컨센서스 (증권사)"):
            gap_str = f"{cv['gap']:+.1f}%" if cv["gap"] is not None else "-"
            gap_col = "#16A34A" if (cv["gap"] or 0) > 0 else "#DC2626" if (cv["gap"] or 0) < 0 else "#6B7280"
            rec_col = ("#16A34A" if cv["rec"] in ("적극 매수", "매수", "매수 우위")
                       else "#DC2626" if cv["rec"] in ("매도", "적극 매도", "매도 우위") else "#6B7280")
            st.markdown(
                f'<div class="card" style="border-left:4px solid {gap_col}">'
                f'<div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px">'
                f'<span style="font-size:18px;font-weight:800;color:{rec_col}">{cv["rec"]}</span>'
                f'<span style="font-size:13px;color:#6B7280">애널리스트 {cv["count"]}명</span></div>'
                f'<div style="margin-top:8px;font-size:14px;color:#374151;line-height:1.9">'
                f'평균 목표가 <b>{fmt_native(cv["target_mean"], market)}</b> '
                f'(<span style="color:{gap_col};font-weight:700">{gap_str}</span> · {cv["gap_label"]})<br>'
                f'최고 {fmt_native(cv["target_high"], market)} · 최저 {fmt_native(cv["target_low"], market)}</div>'
                f'<div class="sub" style="margin-top:8px;line-height:1.6">{cv["interp"]}</div></div>',
                unsafe_allow_html=True)
            st.caption("출처: Yahoo Finance 애널리스트 집계. 참고용 정보입니다.")

    fib = all_ind["fibonacci"]
    with st.expander("📐 지지·저항 전체 · 피보나치"):
        lc1, lc2 = st.columns(2)
        with lc1:
            st.markdown("**🟢 지지 (아래)**")
            if levels["supports"]:
                st.dataframe(pd.DataFrame([
                    {"가격": fmt_native(s["price"], market), "거리": f"{s['dist_pct']:.1f}%", "근거": s["label"]}
                    for s in levels["supports"]]), use_container_width=True, hide_index=True)
            else:
                st.caption("뚜렷한 지지 없음")
        with lc2:
            st.markdown("**🔴 저항 (위)**")
            if levels["resistances"]:
                st.dataframe(pd.DataFrame([
                    {"가격": fmt_native(s["price"], market), "거리": f"+{s['dist_pct']:.1f}%", "근거": s["label"]}
                    for s in levels["resistances"]]), use_container_width=True, hide_index=True)
            else:
                st.caption("뚜렷한 저항 없음")
        if fib:
            st.markdown("**피보나치 되돌림**")
            st.dataframe(pd.DataFrame(
                [{"레벨": k, "가격": fmt_native(v, market)} for k, v in fib["levels"].items()]),
                use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# 페이지: 워치리스트
# ---------------------------------------------------------------------------
def page_watchlist():
    st.title("관심종목")
    st.caption("관심 종목들의 현재가와 기술적 신호를 한눈에 봅니다.")

    wl = load_json(WATCHLIST_FILE, [])

    # 이름으로 검색해서 추가
    with st.expander("🔍 이름으로 검색해서 관심종목 추가", expanded=not wl):
        q = st.text_input("종목 이름", placeholder="예: 삼성전자 · 테슬라 · 비트코인", key="wl_search")
        if q.strip():
            results = fetch_search(q.strip())
            if results:
                with st.spinner("종목 정보 불러오는 중..."):
                    labels, results = search_labels(results)
                sel = st.selectbox("검색 결과 (거래대금 큰 순)", labels, key="wl_search_results")
                if st.button("➕ 관심종목에 추가"):
                    r = results[labels.index(sel)]
                    if any(w.get("symbol") == r["symbol"] and w.get("market") == r["market"] for w in wl):
                        st.warning("이미 있는 종목이에요.")
                    else:
                        wl.append({"name": r["name"], "symbol": r["symbol"], "market": r["market"]})
                        save_json(WATCHLIST_FILE, wl)
                        save_json_cloud("data/watchlist.json", wl, "워치리스트 종목 추가 (대시보드)")
                        st.success(f"{r['name']} 추가됨!")
                        st.rerun()
            else:
                st.caption("결과 없음 — 철자나 한/영 표기를 바꿔보세요.")

    df_edit = pd.DataFrame(wl) if wl else pd.DataFrame(columns=["name", "symbol", "market"])
    edited = st.data_editor(
        df_edit,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "name": st.column_config.TextColumn("이름"),
            "symbol": st.column_config.TextColumn("심볼"),
            "market": st.column_config.SelectboxColumn("시장", options=["KR", "US", "COIN"]),
        },
        key="watchlist_editor",
    )
    _gh_token, _ = gh_config()
    st.caption("☁️ 클라우드 저장 연결됨 — 추가/삭제가 자동 알림에도 반영돼요." if _gh_token
               else "💾 로컬 저장만 가능 (클라우드 반영은 GH_TOKEN 설정 시).")
    if st.button("💾 워치리스트 저장", type="primary"):
        recs = edited.fillna("").to_dict("records")
        save_json(WATCHLIST_FILE, recs)
        ok, info = save_json_cloud("data/watchlist.json", recs, "워치리스트 업데이트 (대시보드)")
        if ok:
            st.success("저장 완료! ☁️ 클라우드에 반영됨 (앱이 잠시 새로고침될 수 있어요)")
        elif info == "no-token":
            st.success("저장 완료! (로컬)")
        else:
            st.warning(f"로컬 저장됨. 단, 클라우드 반영 실패: {info}")

    if edited.empty:
        st.info("관심종목을 추가해 주세요.")
        return

    rows = []
    with st.spinner("신호 계산 중..."):
        for _, r in edited.iterrows():
            sym, mkt = str(r.get("symbol", "")).strip(), str(r.get("market", "")).strip().upper()
            if not sym or mkt not in MARKET_LABELS:
                continue
            df = fetch_ohlcv(sym, mkt, "1y")
            if df.empty:
                rows.append({"이름": r.get("name", sym), "시장": MARKET_LABELS.get(mkt, mkt),
                             "현재가": "-", "신호": "데이터 없음", "상승%": None})
                continue
            res = signals.evaluate(df)
            rows.append({
                "이름": r.get("name", sym),
                "시장": MARKET_LABELS.get(mkt, mkt),
                "현재가": fmt_native(float(df["close"].iloc[-1]), mkt),
                "신호": res["verdict"],
                "상승%": res["up_pct"],
            })

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True, hide_index=True,
        column_config={"상승%": st.column_config.ProgressColumn(
            "상승 우세", min_value=0, max_value=100, format="%.0f%%")},
    )


# ---------------------------------------------------------------------------
# 페이지: 알림 설정
# ---------------------------------------------------------------------------
ALERTS_FILE = DATA_DIR / "alerts.json"


def page_alerts():
    st.title("알림 설정")
    st.caption("신호가 바뀌거나(예: 중립→상승우세) 목표가·손절가에 닿으면 텔레그램으로 알려드려요.")

    # 1) 텔레그램 연결 상태 + 테스트
    if notify.is_configured():
        st.success("텔레그램 연결됨 ✅ (기존 봇으로 알림 전송)")
    else:
        st.warning("텔레그램 토큰/chat_id 미설정 — config/notify.json 또는 환경변수 필요")
    if st.button("📨 테스트 메시지 보내기"):
        ok, info = notify.send("🔔 [테스트] 주식 대시보드 알림이 정상 연결됐어요!")
        (st.success if ok else st.error)(f"테스트 발송: {info}")

    st.divider()

    # 2) 종목별 알림 설정 (워치리스트 + 보유종목) — 현재가 표시 + 버튼/스텝 입력
    st.subheader("종목별 목표가 · 손절가 · 신호알림")
    _gh_token, _ = gh_config()
    if _gh_token:
        st.caption("☁️ 클라우드 저장 연결됨 — 저장하면 자동 알림(GitHub Actions)에도 바로 반영돼요.")
    else:
        st.caption("💾 현재 로컬 저장만 가능 — 폰/클라우드 영구 저장은 Streamlit Secrets에 GH_TOKEN 설정 필요.")
    st.caption("현재가를 참고해 목표가/손절가를 정하세요. 입력칸 ▲▼로 미세조정, 버튼으로 현재가 대비 % 자동입력. "
               "값 0이면 그 알림은 끔. (통화: 미국=USD, 그 외=원)")

    monitored = {}
    for item in load_json(WATCHLIST_FILE, []) + load_json(PORTFOLIO_FILE, []):
        sym = str(item.get("symbol", "")).strip()
        mkt = str(item.get("market", "")).strip().upper()
        if sym and mkt:
            monitored[f"{sym}|{mkt}"] = item.get("name", sym)

    if not monitored:
        st.info("워치리스트나 보유종목을 먼저 추가하면 여기 나타납니다.")
    else:
        existing = load_json(ALERTS_FILE, {})
        with st.spinner("현재가 불러오는 중..."):
            cur_map = {k: fetch_price(k.split("|", 1)[0], k.split("|", 1)[1]) for k in monitored}

        for key, name in monitored.items():
            sym, mkt = key.split("|", 1)
            cur = cur_map.get(key)
            cfg = existing.get(key, {})
            st.session_state.setdefault(f"tgt_{key}", float(cfg.get("target") or 0.0))
            st.session_state.setdefault(f"ent_{key}", float(cfg.get("entry") or 0.0))
            st.session_state.setdefault(f"stop_{key}", float(cfg.get("stop") or 0.0))
            st.session_state.setdefault(f"sig_{key}", bool(cfg.get("signal_alert", True)))
            tick = alert_tick(cur, mkt)
            fmt = "%.2f" if mkt == "US" else "%.0f"

            st.markdown(
                f'<div style="margin-top:6px"><b style="font-size:15px">{html_lib.escape(name)}</b>'
                f'&nbsp; <span style="color:#6B7280">현재가</span> '
                f'<b>{fmt_native(cur, mkt)}</b></div>', unsafe_allow_html=True)
            tc, ec, sc, kc = st.columns([3, 3, 3, 2])
            with tc:
                st.number_input("🎯 목표가 (이상이면 알림)", key=f"tgt_{key}",
                                min_value=0.0, step=float(tick), format=fmt)
                bb = st.columns(3)
                bb[0].button("현재가", key=f"tc0_{key}", disabled=cur is None, use_container_width=True,
                             on_click=set_price_pct, args=(f"tgt_{key}", cur, 0, mkt))
                bb[1].button("+5%", key=f"tp5_{key}", disabled=cur is None, use_container_width=True,
                             on_click=set_price_pct, args=(f"tgt_{key}", cur, 5, mkt))
                bb[2].button("+10%", key=f"tp10_{key}", disabled=cur is None, use_container_width=True,
                             on_click=set_price_pct, args=(f"tgt_{key}", cur, 10, mkt))
            with ec:
                st.number_input("🟢 매수자리 (이하면 알림)", key=f"ent_{key}",
                                min_value=0.0, step=float(tick), format=fmt,
                                help="현재가가 이 값까지 내려오면 '매수 자리' 알림")
                bb = st.columns(3)
                bb[0].button("-3%", key=f"em3_{key}", disabled=cur is None, use_container_width=True,
                             on_click=set_price_pct, args=(f"ent_{key}", cur, -3, mkt))
                bb[1].button("-5%", key=f"em5_{key}", disabled=cur is None, use_container_width=True,
                             on_click=set_price_pct, args=(f"ent_{key}", cur, -5, mkt))
                bb[2].button("-10%", key=f"em10_{key}", disabled=cur is None, use_container_width=True,
                             on_click=set_price_pct, args=(f"ent_{key}", cur, -10, mkt))
            with sc:
                st.number_input("🛑 손절가 (이하면 알림)", key=f"stop_{key}",
                                min_value=0.0, step=float(tick), format=fmt)
                bb = st.columns(3)
                bb[0].button("현재가", key=f"sc0_{key}", disabled=cur is None, use_container_width=True,
                             on_click=set_price_pct, args=(f"stop_{key}", cur, 0, mkt))
                bb[1].button("-5%", key=f"sm5_{key}", disabled=cur is None, use_container_width=True,
                             on_click=set_price_pct, args=(f"stop_{key}", cur, -5, mkt))
                bb[2].button("-10%", key=f"sm10_{key}", disabled=cur is None, use_container_width=True,
                             on_click=set_price_pct, args=(f"stop_{key}", cur, -10, mkt))
            with kc:
                st.checkbox("📈 신호변화\n알림", key=f"sig_{key}")
            st.divider()

        if st.button("💾 알림 설정 저장", type="primary"):
            cfg = {}
            for key in monitored:
                ent = {"signal_alert": bool(st.session_state.get(f"sig_{key}", True))}
                t = st.session_state.get(f"tgt_{key}") or 0
                e = st.session_state.get(f"ent_{key}") or 0
                s = st.session_state.get(f"stop_{key}") or 0
                if t > 0:
                    ent["target"] = float(t)
                if e > 0:
                    ent["entry"] = float(e)
                if s > 0:
                    ent["stop"] = float(s)
                cfg[key] = ent
            save_json(ALERTS_FILE, cfg)  # 로컬(또는 현재 컨테이너) 저장
            ok, info = save_json_cloud("data/alerts.json", cfg, "알림 설정 업데이트 (대시보드)")
            if ok:
                st.success("저장 완료! ☁️ 클라우드에 반영됨 — 다음 점검(최대 30분)부터 자동 알림 적용. "
                           "(앱이 잠시 새로고침될 수 있어요)")
            elif info == "no-token":
                st.success("저장 완료! (로컬) — 클라우드 자동 알림 반영은 GH_TOKEN 설정 후 가능해요.")
            else:
                st.warning(f"로컬 저장됨. 단, 클라우드 반영 실패: {info}")

    st.divider()

    # 3) 지금 한 번 점검
    st.subheader("수동 점검")
    if st.button("🔍 지금 한 번 점검하고 변화 있으면 발송"):
        with st.spinner("점검 중..."):
            msgs = alert_engine.run_once(send_telegram=True)
        if msgs:
            st.success(f"알림 {len(msgs)}건 발송!")
            for m in msgs:
                st.text(m)
        else:
            st.info("변화 없음 (직전 점검 대비 바뀐 신호/가격 없음).")

    # 4) 자동 실행 안내
    with st.expander("⏰ 자동으로 주기적 알림 받기 (설정 방법)"):
        st.markdown(
            "**PowerShell에서 반복 실행 (PC 켜둔 동안):**\n"
            "```\n.venv\\Scripts\\python alerts_run.py --loop 15\n```\n"
            "15분마다 점검합니다. 창을 닫으면 멈춰요.\n\n"
            "**완전 자동(작업 스케줄러):** `ALERTS.md` 안내 참고. "
            "PC를 끄는 시간이 많으면 클라우드 배포가 더 좋아요."
        )


# ---------------------------------------------------------------------------
# 페이지: 시장 개요 (거시 흐름)
# ---------------------------------------------------------------------------
def page_market():
    st.title("시장 개요")
    st.caption("주요 지수·환율·심리지표와 시장 뉴스로 전체 장 분위기를 봅니다.")

    # 주요 지수
    st.subheader("주요 지수 · 환율")
    with st.spinner("지수 불러오는 중..."):
        indices = fetch_indices()
    cols = st.columns(3)
    for i, idx in enumerate(indices):
        with cols[i % 3]:
            val = idx.get("value")
            chg = idx.get("change_pct")
            val_s = f"{val:,.2f}" if val is not None else "-"
            delta = f"{chg:+.2f}%" if chg is not None else None
            st.metric(idx["name"], val_s, delta)

    # 코인 공포탐욕지수
    fg = fetch_fear_greed()
    if fg:
        st.subheader("코인 공포·탐욕 지수")
        st.metric("Fear & Greed", f"{fg['value']} / 100", fg["label"])
        st.progress(fg["value"] / 100)
        st.caption("0=극단적 공포(과매도) · 100=극단적 탐욕(과열)")

    # 거시 뉴스
    st.subheader("시장 뉴스")
    with st.spinner("뉴스 불러오는 중..."):
        macro = market_mod.get_macro_news(limit=10)
    render_news(macro, "뉴스를 불러오지 못했어요.")


# ---------------------------------------------------------------------------
# 종목 선택 위젯 (검색 + 보유/관심 빠른선택) — 여러 페이지 공용
# ---------------------------------------------------------------------------
def symbol_picker(key_prefix: str, default=("005930", "KR", "삼성전자")):
    """이름검색 + 보유/관심 빠른선택. (symbol, market, dispname) 반환."""
    pf = load_json(PORTFOLIO_FILE, [])
    wl = load_json(WATCHLIST_FILE, [])
    options = {}
    for item in pf + wl:
        nm = item.get("name", item["symbol"])
        options[f"{nm} ({item['symbol']}/{item['market']})"] = (item["symbol"], item["market"], nm)

    symbol, market, dispname = default
    col1, col2 = st.columns(2)
    picked = None
    with col1:
        q = st.text_input("🔍 이름으로 검색", placeholder="예: 삼성전자 · 테슬라 · 비트코인",
                          key=f"{key_prefix}_q")
        if q.strip():
            results = fetch_search(q.strip())
            if results:
                with st.spinner("종목 정보 불러오는 중..."):
                    labels, results = search_labels(results)
                sel = st.selectbox("검색 결과 (거래대금 큰 순)", labels, key=f"{key_prefix}_sel")
                r = results[labels.index(sel)]
                picked = (r["symbol"], r["market"], r["name"])
            else:
                st.caption("결과 없음 — 철자나 한/영 표기를 바꿔보세요.")
    with col2:
        quick = st.selectbox("또는 보유·관심 종목", ["— 선택 안 함 —"] + list(options.keys()),
                             key=f"{key_prefix}_quick")
    if picked:
        return picked
    if quick != "— 선택 안 함 —":
        return options[quick]
    return symbol, market, dispname


# ---------------------------------------------------------------------------
# 페이지: 백테스트 (신호 신뢰도 검증)
# ---------------------------------------------------------------------------
def make_backtest_chart(res: dict, dispname: str) -> go.Figure:
    """자산곡선(전략 vs 보유) + 종합신호 점수 2단 차트."""
    dates = res["dates"]
    p = res["params"]
    is_dip = res.get("strategy") == "dip"
    strat_name = "눌림목 전략" if is_dip else "신호 전략"
    row2_title = "고점 대비 낙폭(%) · 진입 기준선" if is_dip else "종합 신호 점수"
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06,
        row_heights=[0.68, 0.32],
        subplot_titles=(f"자산곡선 — {strat_name} vs 그냥 보유 (시작=100)", row2_title),
    )
    fig.add_trace(go.Scatter(x=dates, y=res["equity"] * 100, name=strat_name,
                             line=dict(color="#2563EB", width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=res["price"] * 100, name="그냥 보유(Buy&Hold)",
                             line=dict(color="#9CA3AF", width=1.6, dash="dot")), row=1, col=1)
    fig.add_hline(y=100, line_dash="dot", line_color="#D1D5DB", row=1, col=1)

    if is_dip:
        fig.add_trace(go.Scatter(x=dates, y=res["dd"], name="고점대비 낙폭",
                                 line=dict(color="#8e44ad", width=1.2)), row=2, col=1)
        fig.add_hline(y=-p["dip_pct"], line_dash="dash", line_color="rgba(229,57,53,0.6)",
                      annotation_text=f"매수 -{p['dip_pct']:.0f}%", annotation_position="right", row=2, col=1)
        fig.add_hline(y=0, line_dash="dot", line_color="#D1D5DB", row=2, col=1)
    else:
        fig.add_trace(go.Scatter(x=dates, y=res["signal"], name="종합 신호",
                                 line=dict(color="#8e44ad", width=1.2)), row=2, col=1)
        fig.add_hline(y=p["buy_th"], line_dash="dash", line_color="rgba(229,57,53,0.6)",
                      annotation_text=f"매수 {p['buy_th']:.0f}", annotation_position="right", row=2, col=1)
        fig.add_hline(y=p["sell_th"], line_dash="dash", line_color="rgba(37,99,235,0.6)",
                      annotation_text=f"청산 {p['sell_th']:.0f}", annotation_position="right", row=2, col=1)
    fig.update_layout(
        height=560, hovermode="x unified", dragmode="pan",
        legend=dict(orientation="h", yanchor="top", y=-0.08, xanchor="left", x=0,
                    font=dict(size=10)),
        margin=dict(l=8, r=70, t=54, b=40),
    )
    return fig


def page_backtest():
    st.title("백테스트 — 신호대로 매매했다면?")
    st.caption("이 대시보드의 종합 신호대로 과거에 매매했다면 수익률이 어땠을지 검증합니다. "
               "신호의 신뢰도를 가늠하는 참고용이며, 과거 성과가 미래를 보장하지 않습니다.")

    symbol, market, dispname = symbol_picker("bt")

    strat = st.radio("전략", ["📊 신호 전략", "📉 눌림목 매수 전략"], horizontal=True,
                     help="신호: 종합신호 점수로 매매 / 눌림목: 고점 대비 하락 시 매수 → 익절·손절")
    period_label = st.selectbox("검증 기간", ["1년", "2년", "5년"], index=1)
    period = {"1년": "1y", "2년": "2y", "5년": "5y"}[period_label]
    is_dip = strat.startswith("📉")
    strat_label = "눌림목 전략" if is_dip else "신호 전략"

    if is_dip:
        c1, c2, c3 = st.columns(3)
        dip = c1.slider("눌림목 깊이 (고점대비 −%)", 3, 20, 7, step=1,
                        help="최근 20봉 고점 대비 이만큼 하락하면 매수")
        take = c2.slider("익절 (+%)", 3, 30, 10, step=1, help="매수가 대비 이만큼 오르면 청산")
        stop = c3.slider("손절 (−%)", 3, 20, 7, step=1, help="매수가 대비 이만큼 빠지면 청산")
        with st.spinner("과거 데이터로 시뮬레이션 중..."):
            res = run_dip_backtest_cached(symbol, market, period, float(dip), float(take), float(stop))
    else:
        c1, c2, c3 = st.columns(3)
        buy_th = c1.slider("매수 기준", 50, 80, 60, step=5, help="종합 신호 점수가 이 값 이상이면 매수")
        sell_th = c2.slider("청산 기준", 30, 50, 45, step=5, help="종합 신호 점수가 이 값 이하이면 청산")
        fee = c3.slider("거래비용(편도 %)", 0.0, 0.5, 0.1, step=0.05, help="수수료+슬리피지 가정")
        with st.spinner("과거 데이터로 시뮬레이션 중... (기간이 길면 수십 초 걸릴 수 있어요)"):
            res = run_backtest_cached(symbol, market, period, float(buy_th), float(sell_th), float(fee))

    if not res.get("ok"):
        st.warning(res.get("reason", "백테스트를 실행할 수 없어요."))
        return

    m = res["metrics"]
    st.markdown(
        f'<div style="font-size:15px;color:#6B7280;margin:.2rem 0 1rem">'
        f'<b style="color:#111827;font-size:17px">{dispname}</b>&nbsp; {symbol} · {market} '
        f'· {period_label} 검증</div>', unsafe_allow_html=True)

    # 핵심 비교 카드: 전략 vs 보유
    diff = m["strategy_return"] - m["buyhold_return"]
    won = diff >= 0
    cc = st.columns(2)
    with cc[0]:
        st.markdown(
            f'<div class="card" style="border-top:4px solid #2563EB">'
            f'<div class="lbl">{strat_label} 수익률</div>'
            f'<div class="val {_chg_cls(m["strategy_return"])}">{m["strategy_return"]:+.1f}%</div>'
            f'<div class="sub">최대낙폭(MDD) {m["strategy_mdd"]:.1f}% · '
            f'노출도 {m["exposure"]:.0f}%</div></div>', unsafe_allow_html=True)
    with cc[1]:
        st.markdown(
            f'<div class="card" style="border-top:4px solid #9CA3AF">'
            f'<div class="lbl">그냥 보유(Buy&amp;Hold)</div>'
            f'<div class="val {_chg_cls(m["buyhold_return"])}">{m["buyhold_return"]:+.1f}%</div>'
            f'<div class="sub">최대낙폭(MDD) {m["buyhold_mdd"]:.1f}%</div></div>',
            unsafe_allow_html=True)

    verdict = (f"{strat_label}이 그냥 보유보다 <b>{diff:+.1f}%p</b> "
               f"{'앞섰습니다 👍' if won else '뒤졌습니다'}.")
    sub = ("이 종목·기간에선 이 전략이 더 나았어요. 다만 표본이 한정적이라 맹신은 금물."
           if won else
           "이 종목·기간에선 그냥 들고 있는 게 더 나았어요. 추세장에선 흔한 결과예요.")
    box_color = "#16A34A" if won else "#B45309"
    st.markdown(
        f'<div class="summary-box" style="border-left-color:{box_color};margin-top:12px">'
        f'{verdict}<br><span style="color:#6B7280;font-size:14px">{sub}</span></div>',
        unsafe_allow_html=True)

    st.write("")
    st.plotly_chart(make_backtest_chart(res, dispname), use_container_width=True, config=CHART_CONFIG)

    # 보조 지표
    g = st.columns(4)
    g[0].metric("거래 횟수", f"{m['n_trades']}회")
    g[1].metric("승률", f"{m['win_rate']:.0f}%" if m["win_rate"] is not None else "-")
    cagr_s = f"{m['strategy_cagr']:+.1f}%" if m["strategy_cagr"] is not None else "-"
    cagr_b = f"{m['buyhold_cagr']:+.1f}%" if m["buyhold_cagr"] is not None else "-"
    g[2].metric("전략 연환산(CAGR)", cagr_s)
    g[3].metric("보유 연환산(CAGR)", cagr_b)

    # 거래 내역
    trades = res["trades"]
    if trades:
        with st.expander(f"📋 거래 내역 ({len(trades)}건) 보기"):
            tdf = pd.DataFrame([{
                "진입일": t["entry_date"].strftime("%Y-%m-%d"),
                "진입가": fmt_native(t["entry_price"], market),
                "청산일": t["exit_date"].strftime("%Y-%m-%d") + (" (보유중)" if t.get("open") else ""),
                "청산가": fmt_native(t["exit_price"], market),
                "수익률": t["ret_pct"],
                "보유봉": t["bars"],
            } for t in trades])
            st.dataframe(
                tdf, use_container_width=True, hide_index=True,
                column_config={"수익률": st.column_config.NumberColumn("수익률", format="%.1f%%")},
            )
    else:
        st.caption("이 기간에 신호 기준을 충족한 매매가 한 번도 없었어요. 기준을 완화해 보세요.")

    st.caption("⚠️ 종가 기준 체결을 가정한 단순 시뮬레이션입니다. 실제 매매에는 세금·슬리피지·"
               "체결 지연이 추가되며, 표본 구간에 따라 결과가 달라집니다. 참고용으로만 보세요.")


# ---------------------------------------------------------------------------
# 페이지: 스캐너 (관심·보유 종목 신호 랭킹)
# ---------------------------------------------------------------------------
def page_scanner():
    st.title("스캐너 — 신호 강한 순 랭킹")
    st.caption("워치리스트와 보유 종목의 종합 신호를 한 번에 계산해 상승 신호가 강한 순으로 정렬합니다.")

    # 대상 종목 = 워치리스트 + 보유종목 (중복 제거)
    universe = {}
    for item in load_json(WATCHLIST_FILE, []) + load_json(PORTFOLIO_FILE, []):
        sym = str(item.get("symbol", "")).strip()
        mkt = str(item.get("market", "")).strip().upper()
        if sym and mkt in MARKET_LABELS:
            universe[(sym, mkt)] = item.get("name", sym)

    if not universe:
        st.info("워치리스트나 보유 종목을 먼저 추가하면 여기서 한꺼번에 랭킹을 볼 수 있어요. "
                "(⭐ 워치리스트 / 💰 내 자산 메뉴에서 추가)")
        return

    cflt, csort = st.columns([1.4, 1])
    with cflt:
        flt = st.radio("필터", ["전체", "상승 우세만", "하락 우세만"], horizontal=True)
    with csort:
        only_strong = st.checkbox("강한 신호만 (점수 65↑ 또는 35↓)", value=False)

    rows = []
    prog = st.progress(0.0, text="신호 계산 중...")
    items = list(universe.items())
    for i, ((sym, mkt), name) in enumerate(items):
        prog.progress((i + 1) / len(items), text=f"신호 계산 중... ({name})")
        df = fetch_ohlcv(sym, mkt, "1y")
        if df.empty:
            rows.append({"이름": name, "시장": MARKET_LABELS.get(mkt, mkt), "현재가": "-",
                         "상승%": None, "신호": "데이터 없음", "RSI": None,
                         "추세": "-", "저항까지": None, "_sym": sym, "_mkt": mkt})
            continue
        all_ind = ind.compute_all(df)
        res = signals.evaluate(df)
        levels = lv_mod.compute_levels(df, all_ind)
        rsi_s = all_ind.get("rsi")
        rsi_v = float(rsi_s.dropna().iloc[-1]) if rsi_s is not None and not rsi_s.dropna().empty else None
        slope = all_ind.get("trend_slope")
        trend = ("상승" if slope and slope > 0.15 else "하락" if slope and slope < -0.15 else "횡보")
        nres = levels["resistances"][0]["dist_pct"] if levels.get("resistances") else None
        rows.append({
            "이름": name, "시장": MARKET_LABELS.get(mkt, mkt),
            "현재가": fmt_native(float(df["close"].iloc[-1]), mkt),
            "상승%": res["up_pct"], "신호": res["verdict"],
            "RSI": round(rsi_v) if rsi_v is not None else None,
            "추세": trend, "저항까지": nres,
            "_sym": sym, "_mkt": mkt,
        })
    prog.empty()

    # 필터링
    def keep(r):
        up = r["상승%"]
        if up is None:
            return flt == "전체" and not only_strong
        if flt == "상승 우세만" and up < 55:
            return False
        if flt == "하락 우세만" and up > 45:
            return False
        if only_strong and not (up >= 65 or up <= 35):
            return False
        return True

    shown = [r for r in rows if keep(r)]
    shown.sort(key=lambda r: (r["상승%"] is not None, r["상승%"] or 0), reverse=True)

    if not shown:
        st.caption("조건에 맞는 종목이 없어요. 필터를 바꿔보세요.")
        return

    view = pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in shown])
    st.dataframe(
        view, use_container_width=True, hide_index=True,
        column_config={
            "상승%": st.column_config.ProgressColumn("종합 신호", min_value=0, max_value=100, format="%.0f%%"),
            "저항까지": st.column_config.NumberColumn("저항까지", format="+%.1f%%", help="가장 가까운 저항선까지 거리"),
            "RSI": st.column_config.NumberColumn("RSI"),
        },
    )
    st.caption(f"총 {len(shown)}개 · 종합 신호 점수 높은 순. 자세히 보려면 ‘기술적 분석’에서 해당 종목을 검색하세요. "
               "신호는 보조 지표이며 투자 책임은 본인에게 있습니다.")


# ---------------------------------------------------------------------------
# 페이지: 종목 비교
# ---------------------------------------------------------------------------
def page_compare():
    st.title("종목 비교")
    st.caption("관심·보유 종목을 2~4개 골라 신호·지표·수익률을 나란히 비교합니다.")

    pf = load_json(PORTFOLIO_FILE, [])
    wl = load_json(WATCHLIST_FILE, [])
    options = {}
    for item in wl + pf:
        nm = item.get("name", item["symbol"])
        key = f"{nm} ({item['symbol']}/{item['market']})"
        options[key] = (item["symbol"], item["market"], nm)
    if not options:
        st.info("워치리스트나 보유종목을 먼저 추가해 주세요.")
        return

    default = list(options.keys())[: min(3, len(options))]
    picked = st.multiselect("비교할 종목 (2~4개)", list(options.keys()),
                            default=default, max_selections=4)
    period_label = st.radio("기간", list(PERIOD_OPTIONS.keys()), index=1, horizontal=True)
    period = PERIOD_OPTIONS[period_label]

    if len(picked) < 2:
        st.info("2개 이상 선택하면 비교가 나타납니다.")
        return

    rows = []
    chart = go.Figure()
    palette = ["#2563EB", "#E53935", "#16A34A", "#CA8A04"]
    with st.spinner("비교 데이터 불러오는 중..."):
        for i, key in enumerate(picked):
            sym, mkt, nm = options[key]
            df = fetch_ohlcv(sym, mkt, period)
            if df.empty:
                continue
            all_ind = ind.compute_all(df)
            res = signals.evaluate(df)
            fund = fetch_fundamentals(sym, mkt) if mkt != "COIN" else {}
            cur = float(df["close"].iloc[-1])
            first = float(df["close"].iloc[0])
            pr = (cur - first) / first * 100 if first else 0.0
            rsi_s = all_ind.get("rsi")
            rsi = float(rsi_s.dropna().iloc[-1]) if rsi_s is not None and not rsi_s.dropna().empty else None
            slope = all_ind.get("trend_slope")
            trend = "상승" if slope and slope > 0.15 else "하락" if slope and slope < -0.15 else "횡보"
            pos = fund.get("week52_pos")
            rows.append({
                "종목": nm,
                "현재가": fmt_native(cur, mkt),
                f"{period_label} 수익률": round(pr, 1),
                "종합신호": res["up_pct"],
                "RSI": round(rsi) if rsi is not None else None,
                "추세": trend,
                "52주위치": (round(pos * 100) if pos is not None else None),
                "목표가괴리": (round(fund["target_upside"], 1) if fund.get("target_upside") is not None else None),
            })
            chart.add_trace(go.Scatter(x=df.index, y=df["close"] / first * 100, name=nm,
                                       line=dict(color=palette[i % len(palette)], width=1.8)))

    if not rows:
        st.warning("데이터를 불러오지 못했어요.")
        return

    st.dataframe(
        pd.DataFrame(rows), use_container_width=True, hide_index=True,
        column_config={
            "종합신호": st.column_config.ProgressColumn("종합신호", min_value=0, max_value=100, format="%.0f%%"),
            f"{period_label} 수익률": st.column_config.NumberColumn(f"{period_label} 수익률", format="%+.1f%%"),
            "52주위치": st.column_config.NumberColumn("52주위치", format="%d%%", help="0=52주 최저, 100=최고"),
            "목표가괴리": st.column_config.NumberColumn("목표가괴리", format="%+.1f%%", help="전문가 평균 목표가까지 여력(+)/초과(-)"),
        },
    )

    chart.update_layout(
        title=f"정규화 가격 비교 (시작일=100, {period_label})", height=460, hovermode="x unified",
        dragmode="pan", legend=dict(orientation="h", yanchor="top", y=-0.08, xanchor="left", x=0),
        margin=dict(l=8, r=20, t=50, b=40),
    )
    chart.add_hline(y=100, line_dash="dot", line_color="#D1D5DB")
    st.plotly_chart(chart, use_container_width=True, config=CHART_CONFIG)
    st.caption("정규화 = 시작일을 100으로 맞춰 같은 기간 상대 수익률을 비교. 종합신호·지표는 보조 참고용입니다.")


# ---------------------------------------------------------------------------
# 페이지: 종목 발굴 (스크리너)
# ---------------------------------------------------------------------------
DISCOVERY_FILE = DATA_DIR / "discovery.json"


def page_discovery():
    st.title("종목 발굴")
    st.caption("가치(저PER·저PBR·배당·52주 저점) + 타이밍(우상향 추세 속 눌림목)으로 매수 후보를 자동으로 추려요. "
               "매일 밤 스캔 · 투자 권유가 아닌 후보 탐색 참고용입니다.")

    data = load_json(DISCOVERY_FILE, {})
    cands = data.get("candidates", [])
    if not cands:
        st.info("아직 발굴 결과가 없어요. 매일 밤 자동 스캔되며, 깃허브 Actions에서 '종목 발굴 스캔'을 수동 실행할 수도 있어요.")
        return

    st.caption(f"🕒 마지막 스캔: {data.get('generated', '-')} · 대상 {data.get('universe', '?')}종목 · "
               f"후보 {len(cands)}개 (스캔 {data.get('scanned', '?')}, 실패 {data.get('failed', 0)})")

    flt = st.radio("필터", ["🎯 지금 매수자리 (조합)", "💰 가치 상위", "전체"], horizontal=True)
    if flt.startswith("🎯"):
        rows = [c for c in cands if c.get("combo")]
        rows.sort(key=lambda c: (c["value_score"], c.get("up_pct") or 0), reverse=True)
    elif flt.startswith("💰"):
        rows = sorted(cands, key=lambda c: c["value_score"], reverse=True)
    else:
        rows = cands
    if not rows:
        st.caption("조건에 맞는 후보가 없어요. 필터를 바꿔보세요.")
        return

    view = [{
        "종목": c["name"],
        "시장": MARKET_LABELS.get(c["market"], c["market"]),
        "현재가": fmt_native(c["price"], c["market"]),
        "가치점수": c["value_score"],
        "종합신호": c.get("up_pct"),
        "RSI": c.get("rsi"),
        "PER": c.get("per"),
        "PBR": c.get("pbr"),
        "배당%": c.get("div"),
        "52주위치": c.get("week52_pos"),
        "매수자리": "🎯" if c.get("combo") else "",
    } for c in rows]
    st.dataframe(
        pd.DataFrame(view), use_container_width=True, hide_index=True,
        column_config={
            "가치점수": st.column_config.ProgressColumn("가치점수", min_value=0, max_value=100, format="%d",
                                                    help="저평가 정도(0~100): 저PER·저PBR·고배당·52주 저점일수록 높음"),
            "종합신호": st.column_config.ProgressColumn("종합신호", min_value=0, max_value=100, format="%.0f%%"),
            "52주위치": st.column_config.NumberColumn("52주위치", format="%d%%", help="0=52주 최저, 100=최고"),
            "배당%": st.column_config.NumberColumn("배당%", format="%.2f%%"),
        },
    )
    st.caption("🎯 = 장기 우상향 추세 속 단기 눌림목(지금 매수 관심 구간). 가치점수가 높을수록 저평가. "
               "한국주식은 PER/PBR 데이터가 비어 있는 경우가 많아 배당·52주 위치 위주로 평가됩니다. "
               "자세한 분석은 ‘기술적 분석’에서 해당 종목을 검색하세요.")


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------
def _guide_card(title: str, desc: str, accent: str = "#2563EB") -> str:
    return (f'<div class="card" style="border-left:4px solid {accent};margin-bottom:10px">'
            f'<div style="font-weight:700;font-size:16px;color:#111827;margin-bottom:4px">{title}</div>'
            f'<div style="font-size:14px;color:#374151;line-height:1.6">{desc}</div></div>')


def page_guide():
    st.title("사용 가이드")
    st.caption("처음이라면 이 페이지부터! 대시보드 보는 법과 메뉴 5개를 차근차근 알려드려요.")

    st.markdown(
        '<div class="summary-box">이 대시보드는 <b>예측기가 아니라</b>, 한 종목의 '
        '<b>현재 기술적 위치 · 전문가 목표가 괴리 · 관련 뉴스</b>를 한눈에 정리해주는 '
        '<b>투자 보조 도구</b>입니다. 매수/매도를 권하지 않으며, 판단과 책임은 본인에게 있습니다.</div>',
        unsafe_allow_html=True)

    st.subheader("3단계로 시작하기")
    st.markdown(
        _guide_card("1. 종목 고르기",
                    "‘기술적 분석’ 화면에서 검색창에 <b>이름</b>을 입력하세요. "
                    "한국주식은 한글(삼성전자), 미국주식은 영문/한글(apple·테슬라), 코인은 한글/영문(비트코인). "
                    "검색 결과는 <b>거래대금 큰 순</b>으로 정렬돼요.")
        + _guide_card("2. 결론 3카드 먼저 보기",
                      "맨 위 <b>현재 상태 · 진입 매력도 · 위험도</b> 카드만 봐도 5초 안에 감이 와요. "
                      "신호등 색(🟢좋음 🟡보통 🟠주의 🔴위험)으로 표시됩니다.")
        + _guide_card("3. 궁금하면 아래로",
                      "차트 → 종합 총평 → 전문가 의견 → 지지/저항 → 뉴스 순으로 근거가 이어져요. "
                      "표·상세는 접이식이라 필요할 때만 펼치면 됩니다."),
        unsafe_allow_html=True)

    st.subheader("메뉴 9개")
    st.markdown(
        _guide_card("📊 기술적 분석",
                    "한 종목을 깊게 분석. 결론 3카드 → 차트(이동평균·일목·지지저항) → 지표 요약 → "
                    "종합 총평(추세·모멘텀·진입리스크) → 전문가 목표가 괴리율 → 지지/저항 → "
                    "긍정·부정 신호 → 관련 뉴스. <b>이 앱의 핵심 화면</b>이에요.", "#2563EB")
        + _guide_card("🔭 스캐너",
                      "워치리스트와 보유 종목의 종합 신호를 <b>한 번에 계산해 강한 순으로 랭킹</b>해요. "
                      "‘상승 우세만’ 필터로 지금 주목할 종목을 빠르게 추려볼 수 있어요.", "#7C3AED")
        + _guide_card("🔎 발굴",
                      "주요 종목을 매일 밤 자동 스캔해 <b>가치(저PER·저PBR·배당·52주저점) + 타이밍(우상향 속 눌림목)</b> "
                      "기준으로 <b>매수 후보</b>를 추려줘요. 워치리스트 밖에서 새 종목을 찾을 때.", "#0D9488")
        + _guide_card("🧪 백테스트",
                      "‘이 신호대로 과거에 매매했다면?’을 검증해요. <b>신호 전략 vs 그냥 보유</b> 수익률을 "
                      "비교하고 거래 횟수·승률·최대낙폭을 보여줘 <b>신호의 신뢰도</b>를 가늠하게 해줘요. "
                      "과거 성과가 미래를 보장하진 않아요.", "#0891B2")
        + _guide_card("⚖️ 비교",
                      "관심·보유 종목을 2~4개 골라 <b>신호·수익률·지표·정규화 차트</b>를 나란히 비교해요. "
                      "어느 종목이 더 강한지 한눈에.", "#9333EA")
        + _guide_card("🌡️ 시장 개요",
                      "전체 장 분위기. 코스피·코스닥·S&P500·나스닥·환율·VIX 등락률, "
                      "코인 공포·탐욕 지수, 시장 거시 뉴스를 모아 봅니다.", "#16A34A")
        + _guide_card("💰 내 자산",
                      "보유 종목·수량·매입가를 입력하면 현재가 기준 <b>평가액·수익률·자산 비중</b>을 "
                      "자동 계산해요. 미국주식은 원화로 환산됩니다. (표에서 직접 추가/수정 후 저장)", "#CA8A04")
        + _guide_card("⭐ 워치리스트",
                      "관심 종목을 이름으로 검색해 담아두고, 현재가와 종합 신호를 <b>한 줄씩 모아</b> 봅니다.", "#EA580C")
        + _guide_card("🔔 알림 설정",
                      "신호가 바뀌거나(예: 중립→상승 우세) 목표가·손절가에 닿으면 <b>텔레그램으로 알림</b>을 받아요. "
                      "종목별로 목표가/손절가/신호알림을 설정할 수 있습니다.", "#DC2626"),
        unsafe_allow_html=True)

    st.subheader("자주 나오는 용어")
    with st.expander("종합 신호 점수 (0~100)"):
        st.markdown("지표 10여 개가 상승/하락에 투표한 결과를 종합한 값. **100=대부분 상승 신호, 50=반반, "
                    "0=대부분 하락 신호.** ‘오를 확률’이 아니라 **신호가 어느 쪽으로 쏠렸는지**를 나타냅니다.")
    with st.expander("목표가 괴리율"):
        st.markdown("증권사 **평균 목표가**가 현재가보다 얼마나 높은지(낮은지)예요. "
                    "`(평균 목표가 − 현재가) / 현재가`. **+면 상승 여력, −면 현재가가 목표가를 이미 넘었다**는 뜻(과열 가능성). "
                    "‘컨센서스 매수’라도 괴리율이 마이너스면 주의가 필요합니다.")
    with st.expander("지지선 / 저항선"):
        st.markdown("**지지선**은 아래에서 가격을 받쳐줄 가능성이 있는 가격대(하락 위험 기준), "
                    "**저항선**은 위에서 가격을 누를 가능성이 있는 가격대(상승 여력 기준)예요. "
                    "저항까지 여력과 지지까지 위험을 비교해 진입 매력을 가늠합니다.")
    with st.expander("RSI · MACD · 이동평균 · 일목균형표 · ADX"):
        st.markdown("- **RSI**: 0~100, 70↑ 과매수·30↓ 과매도\n"
                    "- **MACD**: 단기·장기 평균 차이로 모멘텀 방향\n"
                    "- **이동평균(정배열)**: 단기>중기>장기선이면 상승 흐름\n"
                    "- **일목균형표(구름대)**: 현재가가 구름 위면 강세\n"
                    "- **ADX**: 추세의 강도(25↑면 추세 뚜렷)\n\n"
                    "각 지표는 화면에서 이름·근거에 마우스를 올리면 설명이 떠요.")
    with st.expander("공포·탐욕 지수 (코인)"):
        st.markdown("시장 심리를 0~100으로 본 지표. **0=극단적 공포(과매도), 100=극단적 탐욕(과열).** "
                    "‘시장 개요’ 화면에서 확인할 수 있어요.")

    st.info("모든 수치는 투자 판단을 돕는 **참고 정보**이며, 수익을 보장하지 않습니다. "
            "데이터: 주식=yfinance, 코인=업비트, 뉴스=Google News, 전문가 의견=Yahoo Finance 집계.")

    if st.button("📊 기술적 분석 화면으로 가기", type="primary"):
        st.session_state["show_guide"] = False
        st.rerun()


def _clear_guide():
    st.session_state["show_guide"] = False


def main():
    bridge_secrets_to_env()
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.sidebar.title("📈 자산 대시보드")

    # 사용 가이드 버튼 (누르면 가이드 페이지로 이동)
    if st.sidebar.button("📖 사용 가이드", use_container_width=True):
        st.session_state["show_guide"] = True

    page = st.sidebar.radio(
        "메뉴", ["기술적 분석", "스캐너", "발굴", "백테스트", "비교", "시장 개요", "내 자산", "워치리스트", "알림 설정"],
        on_change=_clear_guide)
    st.sidebar.divider()
    st.sidebar.caption(
        "데이터: 주식=yfinance, 코인=업비트, 뉴스=Google News.\n"
        "지표는 보조 신호이며 투자 책임은 본인에게 있습니다."
    )

    if st.session_state.get("show_guide"):
        page_guide()
    elif page == "기술적 분석":
        page_analysis()
    elif page == "스캐너":
        page_scanner()
    elif page == "발굴":
        page_discovery()
    elif page == "백테스트":
        page_backtest()
    elif page == "비교":
        page_compare()
    elif page == "시장 개요":
        page_market()
    elif page == "내 자산":
        page_portfolio()
    elif page == "워치리스트":
        page_watchlist()
    else:
        page_alerts()


if __name__ == "__main__":
    main()
