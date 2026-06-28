"""
주식·자산 관리 + 기술적 분석 대시보드
실행:  streamlit run app.py
"""
from __future__ import annotations

import html as html_lib
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src import alerts as alert_engine
from src import backtest as bt_mod
from src import glossary
from src import indicators as ind
from src import levels as lv_mod
from src import market as market_mod
from src import news as news_mod
from src import notify
from src import prices, search, signals
from src import summary as summary_mod

# ---------------------------------------------------------------------------
# 기본 설정 / 경로
# ---------------------------------------------------------------------------
st.set_page_config(page_title="내 주식·자산 대시보드", page_icon="📈", layout="wide")

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


# ---------------------------------------------------------------------------
# 데이터 (캐시)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def fetch_ohlcv(symbol: str, market: str, period: str) -> pd.DataFrame:
    return prices.get_ohlcv(symbol, market, period)


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
    "displaylogo": False,
    "doubleClick": "reset",
    "modeBarButtonsToRemove": ["select2d", "lasso2d"],
    "toImageButtonOptions": {"format": "png", "filename": "chart", "scale": 2},
}


def make_chart(df: pd.DataFrame, all_ind: dict, title: str, levels: dict | None = None) -> go.Figure:
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
    # 일목균형표 구름대
    ichi = all_ind["ichimoku"]
    fig.add_trace(
        go.Scatter(x=df.index, y=ichi["senkou_a"], name="선행A",
                   line=dict(width=0.5, color="rgba(46,204,113,0.5)")),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(x=df.index, y=ichi["senkou_b"], name="선행B", fill="tonexty",
                   fillcolor="rgba(46,204,113,0.12)",
                   line=dict(width=0.5, color="rgba(231,76,60,0.5)")),
        row=1, col=1,
    )

    # --- RSI ---
    fig.add_trace(
        go.Scatter(x=df.index, y=all_ind["rsi"], name="RSI", line=dict(color="#9b59b6")),
        row=2, col=1,
    )
    fig.add_hline(y=70, line_dash="dot", line_color="red", row=2, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="blue", row=2, col=1)

    # --- MACD ---
    macd_df = all_ind["macd"]
    colors = ["#e74c3c" if v >= 0 else "#3498db" for v in macd_df["hist"].fillna(0)]
    fig.add_trace(go.Bar(x=df.index, y=macd_df["hist"], name="히스토그램",
                         marker_color=colors), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=macd_df["macd"], name="MACD",
                             line=dict(color="#2c3e50")), row=3, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=macd_df["signal"], name="시그널",
                             line=dict(color="#e67e22")), row=3, col=1)

    # 지지/저항 수평선 (가까운 것 위주)
    if levels:
        for s in levels.get("resistances", [])[:2]:
            fig.add_hline(y=s["price"], line_dash="dash", line_color="rgba(192,57,43,0.6)",
                          annotation_text=f"저항 {s['price']:,.0f}", annotation_position="right",
                          row=1, col=1)
        for s in levels.get("supports", [])[:2]:
            fig.add_hline(y=s["price"], line_dash="dash", line_color="rgba(41,128,185,0.6)",
                          annotation_text=f"지지 {s['price']:,.0f}", annotation_position="right",
                          row=1, col=1)

    fig.update_layout(
        height=720, xaxis_rangeslider_visible=False, hovermode="x unified",
        dragmode="zoom",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=90, t=70, b=10),  # 오른쪽 지지/저항 라벨이 안 잘리게 여백 확보
    )
    # 빠른 기간 버튼 (가격 차트 위) — 클릭하면 그 구간으로 확대
    fig.update_xaxes(
        rangeselector=dict(
            buttons=[
                dict(count=1, label="1개월", step="month", stepmode="backward"),
                dict(count=3, label="3개월", step="month", stepmode="backward"),
                dict(count=6, label="6개월", step="month", stepmode="backward"),
                dict(count=1, label="1년", step="year", stepmode="backward"),
                dict(step="all", label="전체"),
            ],
            x=0, y=1.08, font=dict(size=11),
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

    period_label = st.radio("기간", list(PERIOD_OPTIONS.keys()), index=1, horizontal=True)
    period = PERIOD_OPTIONS[period_label]

    df = fetch_ohlcv(symbol, market, period)
    if df.empty:
        st.error(f"'{symbol}' ({market}) 데이터를 불러오지 못했어요. 심볼/시장을 확인해 주세요.")
        return

    all_ind = ind.compute_all(df)
    result = signals.evaluate(df)
    levels = lv_mod.compute_levels(df, all_ind)
    cur = float(df["close"].iloc[-1])
    fund = fetch_fundamentals(symbol, market) if market != "COIN" else {}

    # 등락률(전일 대비) · 기간 수익률
    prev = float(df["close"].iloc[-2]) if len(df) >= 2 else cur
    chg = (cur - prev) / prev * 100 if prev else 0.0
    first = float(df["close"].iloc[0]) if len(df) else cur
    pr = (cur - first) / first * 100 if first else 0.0
    mkt_label = {"KR": "KRX", "US": "US", "COIN": "Upbit"}.get(market, market)

    # 종목 한 줄 요약
    st.markdown(
        f'<div style="font-size:15px;color:#6B7280;margin:.2rem 0 1rem">'
        f'<b style="color:#111827;font-size:17px">{dispname}</b>'
        f'&nbsp; {symbol} · {mkt_label}</div>',
        unsafe_allow_html=True,
    )

    # 결론 3카드 (현재 상태 / 진입 매력도 / 위험도) — 5초 브리핑
    for vc, col in zip(summary_mod.verdict_cards(result, levels, all_ind, market), st.columns(3)):
        emoji, color = summary_mod.TRAFFIC[vc["level"]]
        with col:
            st.markdown(
                f'<div class="card" style="border-top:4px solid {color}">'
                f'<div class="lbl">{vc["title"]}</div>'
                f'<div style="font-size:21px;font-weight:700;color:{color};margin:2px 0 8px">'
                f'{emoji} {vc["label"]}</div>'
                f'<div style="font-size:13.5px;color:#374151;line-height:1.55">{vc["text"]}</div></div>',
                unsafe_allow_html=True)

    st.write("")
    # 가격 요약 (작게 — 보조)
    up = result.get("up_pct")
    pc1, pc2, pc3 = st.columns(3)
    with pc1:
        st.markdown(card_html("현재가", fmt_native(cur, market),
                              sub=f'{period_label} 수익률 <span class="{_chg_cls(pr)}">{pr:+.1f}%</span>',
                              val_sm=True), unsafe_allow_html=True)
    with pc2:
        st.markdown(card_html("전일 대비", f"{chg:+.2f}%", sub="전일 종가 대비",
                              value_cls=_chg_cls(chg), val_sm=True), unsafe_allow_html=True)
    with pc3:
        if up is not None:
            fill = "#E53935" if up >= 55 else ("#2563EB" if up < 45 else "#9CA3AF")
            tip = ("지표 10여 개가 상승/하락에 투표한 결과를 0~100으로 종합한 값입니다. "
                   "100=대부분 상승 신호, 50=반반, 0=대부분 하락 신호. "
                   "오를 확률이 아니라 신호 쏠림 정도입니다.")
            st.markdown(
                f'<div class="card" title="{tip}"><div class="lbl">종합 신호 점수 '
                f'<span class="info">ⓘ</span></div>'
                f'<div class="val sm">{up:.0f}<span style="font-size:14px;color:#9CA3AF"> / 100</span></div>'
                f'<div class="scorebar-track" style="margin:9px 0 6px">'
                f'<div class="scorebar-fill" style="width:{up}%;background:{fill}"></div></div>'
                f'<div class="sub">지표 종합 상승 쏠림도 · 100=상승일색, 50=중립</div></div>',
                unsafe_allow_html=True)
        else:
            st.markdown(card_html("종합 신호 점수", "-", val_sm=True), unsafe_allow_html=True)

    st.write("")
    # 메인 차트 (화면 중심)
    st.plotly_chart(make_chart(df, all_ind, f"{dispname} ({symbol})", levels),
                    use_container_width=True, config=CHART_CONFIG)
    cc1, cc2 = st.columns([1, 4])
    with cc1:
        st.button("차트 초기화", help="확대/이동한 차트를 원래대로 되돌립니다", use_container_width=True)
    with cc2:
        st.caption("차트 위 더블클릭=원상복구 · 휠=확대/축소 · 드래그=영역 확대 · 상단 버튼=기간 이동")

    # 지표 요약 카드
    mini = indicator_mini_cards(result, all_ind)
    if mini:
        st.subheader("지표 요약")
        mcols = st.columns(len(mini))
        for col, m in zip(mcols, mini):
            with col:
                st.markdown(card_html(m["name"], m["value"], sub=m["sub"],
                                      value_cls=m["cls"], val_sm=True), unsafe_allow_html=True)

    # 종합 총평 (추세 / 모멘텀 / 진입 리스크 3단)
    st.subheader("종합 총평")
    st.markdown(
        f'<div class="summary-box">{summary_mod.build_summary(result, levels, all_ind, fund, market)}</div>',
        unsafe_allow_html=True,
    )
    st.caption("기술적 지표를 자동 정리한 참고 해석입니다. 투자 판단과 책임은 본인에게 있습니다.")

    # 전문가(애널리스트) 의견 — 컨센서스 괴리율 중심
    cv = summary_mod.consensus_view(fund, market)
    if cv:
        st.subheader("전문가 의견 (증권사 컨센서스)")
        tone_color = {"warn": "#E53935", "pos": "#2563EB", "calm": "#6B7280"}
        gap_color = tone_color.get(cv["tone"], "#6B7280")
        gap_str = f"{cv['gap']:+.1f}%" if cv["gap"] is not None else "-"
        rec_color = ("#16A34A" if cv["rec"] in ("적극 매수", "매수", "매수 우위")
                     else "#E53935" if cv["rec"] in ("매도", "적극 매도", "매도 우위") else "#6B7280")

        # 괴리율 — 가장 강조 (풀폭 카드)
        st.markdown(
            f'<div class="card" style="border-left:5px solid {gap_color}">'
            f'<div class="lbl">현재가 대비 평균 목표가 괴리율</div>'
            f'<div class="val" style="color:{gap_color}">{gap_str}</div>'
            f'<div class="sub">{cv["gap_label"]} · 현재가 {fmt_native(cv["current"], market)} '
            f'· 평균 목표가 {fmt_native(cv["target_mean"], market)}</div></div>',
            unsafe_allow_html=True,
        )
        st.write("")
        cols = st.columns(5)
        cols[0].markdown(
            f'<div class="card"><div class="lbl">컨센서스 등급</div>'
            f'<div class="val sm" style="color:{rec_color}">{cv["rec"]}</div></div>',
            unsafe_allow_html=True)
        cols[1].markdown(card_html("애널리스트 수", f"{cv['count']}명", val_sm=True), unsafe_allow_html=True)
        cols[2].markdown(card_html("평균 목표가", fmt_native(cv["target_mean"], market), val_sm=True), unsafe_allow_html=True)
        cols[3].markdown(card_html("최고 목표가", fmt_native(cv["target_high"], market), val_sm=True), unsafe_allow_html=True)
        cols[4].markdown(card_html("최저 목표가", fmt_native(cv["target_low"], market), val_sm=True), unsafe_allow_html=True)

        st.markdown(
            f'<div style="margin-top:12px;padding:14px 18px;border-radius:10px;'
            f'background:#F9FAFB;border:1px solid #E5E7EB;color:#374151;line-height:1.65">'
            f'{cv["interp"]}</div>', unsafe_allow_html=True)
        st.caption("증권사 애널리스트 투자의견·목표주가 평균 (출처: Yahoo Finance 집계). 참고용 정보입니다.")

    # 기업 지표 (펀더멘털) — 코인 제외
    if market != "COIN" and fund:
        st.subheader("기업 지표")
        f1, f2, f3, f4 = st.columns(4)
        per = fund.get("per"); pbr = fund.get("pbr")
        f1.metric("PER", f"{per:.1f}" if per is not None else "-")
        f2.metric("PBR", f"{pbr:.2f}" if pbr is not None else "-")
        f3.metric("시가총액", fmt_marketcap(fund.get("market_cap"), market))
        dy = fund.get("dividend_yield")  # yfinance가 %단위로 반환 (예: 0.42 = 0.42%)
        f4.metric("배당수익률", f"{dy:.2f}%" if dy is not None else "-")
        pos = fund.get("week52_pos")
        if pos is not None:
            lo = fmt_native(fund.get("week52_low"), market)
            hi = fmt_native(fund.get("week52_high"), market)
            st.caption(f"52주 최저 {lo} ─ 현재 위치 {pos*100:.0f}% ─ 최고 {hi}")
            st.progress(pos)

    # 지표별 신호 — 긍정/부정 한눈 요약 먼저
    st.subheader("지표별 신호")
    pos_sig, neg_sig = summary_mod.signal_split(result)
    ps1, ps2 = st.columns(2)
    with ps1:
        items = "".join(f"<li>{html_lib.escape(s)}</li>" for s in pos_sig) or "<li style='color:#9CA3AF'>없음</li>"
        st.markdown(
            f'<div class="card" style="border-top:4px solid #E53935">'
            f'<div class="lbl" style="color:#E53935">긍정 신호 {len(pos_sig)}</div>'
            f'<ul style="margin:6px 0 0 -8px;font-size:14px;color:#374151;line-height:1.7">{items}</ul></div>',
            unsafe_allow_html=True)
    with ps2:
        items = "".join(f"<li>{html_lib.escape(s)}</li>" for s in neg_sig) or "<li style='color:#9CA3AF'>없음</li>"
        st.markdown(
            f'<div class="card" style="border-top:4px solid #2563EB">'
            f'<div class="lbl" style="color:#2563EB">부정 신호 {len(neg_sig)}</div>'
            f'<ul style="margin:6px 0 0 -8px;font-size:14px;color:#374151;line-height:1.7">{items}</ul></div>',
            unsafe_allow_html=True)

    # 상세 근거 테이블 (중요도 별점)
    with st.expander("지표별 상세 근거 보기 (중요도·해설)", expanded=False):
        st.caption("지표 이름·근거에 마우스를 올리면 설명이 떠요. (폰은 아래 '지표 설명 펼쳐보기' 참고)")
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
                f'<td title="{name_tip}"><b>{html_lib.escape(name)}</b>'
                '<span class="info">ⓘ</span></td>'
                f'<td style="color:{color};font-weight:600;white-space:nowrap">{label}</td>'
                f'<td title="{why_tip}">{detail}<span class="info">ⓘ</span></td>'
                f'<td style="white-space:nowrap" title="중요도 {imp}">'
                f'<span style="color:#F59E0B">{stars}</span> <span class="info">{imp}</span></td>'
                "</tr>"
            )
        table_html = f"""
        <style>
        table.sig {{ width:100%; border-collapse:collapse; font-size:0.92rem;
                     border:1px solid #E5E7EB; border-radius:12px; overflow:hidden; }}
        table.sig th, table.sig td {{ padding:10px 12px; border-bottom:1px solid #F1F3F5; text-align:left; }}
        table.sig th {{ background:#F9FAFB; font-weight:600; color:#6B7280; }}
        table.sig tr:last-child td {{ border-bottom:none; }}
        table.sig tr:hover td {{ background:#FAFBFC; }}
        table.sig td[title] {{ cursor:help; }}
        .info {{ color:#9CA3AF; font-size:0.8em; margin-left:4px; }}
        </style>
        <table class="sig">
          <tr><th>지표</th><th>신호</th><th>근거</th><th>중요도</th></tr>
          {rows_html}
        </table>
        """
        st.markdown(table_html, unsafe_allow_html=True)

    # 모바일/처음 사용자용 — 지표별 정의 + 현재 신호 해설 펼쳐보기
    with st.expander("📖 지표 설명 펼쳐보기 (처음이라면 여기!)"):
        for v in result["votes"]:
            label, color = level_disp(v["signal"], v["strength"])
            st.markdown(
                f"**{v['name']}** — <span style='color:{color};font-weight:600'>{label}</span>  \n"
                f"· *지표란?* {glossary.explain(v['name'])}  \n"
                f"· *지금 이 신호는?* {glossary.rationale(v['name'], v['signal'])}",
                unsafe_allow_html=True,
            )
            st.divider()

    # 주요 가격대 (지지/저항) — 핵심 카드 먼저, 상세는 아래 테이블
    st.subheader("주요 가격대 (지지·저항)")
    nsup = levels["supports"][0] if levels["supports"] else None
    nres = levels["resistances"][0] if levels["resistances"] else None
    kc1, kc2 = st.columns(2)
    with kc1:
        if nsup:
            st.markdown(
                f'<div class="card" style="border-top:4px solid #2563EB">'
                f'<div class="lbl">가장 가까운 지지</div>'
                f'<div class="val sm">{fmt_native(nsup["price"], market)}</div>'
                f'<div class="sub">현재가 대비 <span class="down">{nsup["dist_pct"]:.1f}%</span> · 하락 위험</div></div>',
                unsafe_allow_html=True)
        else:
            st.markdown(card_html("가장 가까운 지지", "-", sub="최근 저점 부근", val_sm=True), unsafe_allow_html=True)
    with kc2:
        if nres:
            st.markdown(
                f'<div class="card" style="border-top:4px solid #E53935">'
                f'<div class="lbl">가장 가까운 저항</div>'
                f'<div class="val sm">{fmt_native(nres["price"], market)}</div>'
                f'<div class="sub">현재가 대비 <span class="up">+{nres["dist_pct"]:.1f}%</span> · 상승 여력</div></div>',
                unsafe_allow_html=True)
        else:
            st.markdown(card_html("가장 가까운 저항", "-", sub="신고가권", val_sm=True), unsafe_allow_html=True)
    st.caption("저항선까지의 상승 여력과 지지선까지의 하락 위험을 참고할 수 있습니다. 아래 표에서 더 많은 가격대를 확인하세요.")

    lc1, lc2 = st.columns(2)
    with lc1:
        st.markdown("**🔵 지지 (아래)** — 현재가가 내려오면 주목")
        if levels["supports"]:
            sdf = pd.DataFrame([
                {"가격": fmt_native(s["price"], market), "거리": f"{s['dist_pct']:.1f}%", "근거": s["label"]}
                for s in levels["supports"]
            ])
            st.dataframe(sdf, use_container_width=True, hide_index=True)
        else:
            st.caption("뚜렷한 지지 없음 (현재가가 최근 저점 부근)")
    with lc2:
        st.markdown("**🔴 저항 (위)** — 돌파해야 더 오름")
        if levels["resistances"]:
            rdf = pd.DataFrame([
                {"가격": fmt_native(s["price"], market), "거리": f"+{s['dist_pct']:.1f}%", "근거": s["label"]}
                for s in levels["resistances"]
            ])
            st.dataframe(rdf, use_container_width=True, hide_index=True)
        else:
            st.caption("뚜렷한 저항 없음 (현재가가 최근 고점 부근)")

    fib = all_ind["fibonacci"]
    if fib:
        with st.expander("📐 피보나치 되돌림 전체 레벨 보기"):
            flevels = pd.DataFrame(
                [{"레벨": k, "가격": fmt_native(v, market)} for k, v in fib["levels"].items()]
            )
            st.dataframe(flevels, use_container_width=True, hide_index=True)

    # 관련 뉴스 — 분위기 요약 먼저, 원문 링크 아래
    st.subheader("관련 뉴스")
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
    if st.button("💾 워치리스트 저장", type="primary"):
        save_json(WATCHLIST_FILE, edited.fillna("").to_dict("records"))
        st.success("저장 완료!")

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

    # 2) 종목별 알림 설정 (워치리스트 + 보유종목)
    st.subheader("종목별 목표가 · 손절가 · 신호알림")
    st.caption("목표가/손절가는 해당 시장 통화 기준(미국=USD, 그 외=원). 비워두면 그 알림은 끔.")
    monitored = {}
    for item in load_json(WATCHLIST_FILE, []) + load_json(PORTFOLIO_FILE, []):
        sym = str(item.get("symbol", "")).strip()
        mkt = str(item.get("market", "")).strip().upper()
        if sym and mkt:
            monitored[f"{sym}|{mkt}"] = item.get("name", sym)

    existing = load_json(ALERTS_FILE, {})
    rows = []
    for key, name in monitored.items():
        sym, mkt = key.split("|", 1)
        cfg = existing.get(key, {})
        rows.append({
            "이름": name, "심볼": sym, "시장": mkt,
            "목표가": cfg.get("target"), "손절가": cfg.get("stop"),
            "신호알림": cfg.get("signal_alert", True),
        })
    df_edit = pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["이름", "심볼", "시장", "목표가", "손절가", "신호알림"])

    edited = st.data_editor(
        df_edit, use_container_width=True, hide_index=True,
        disabled=["이름", "심볼", "시장"],
        column_config={
            "목표가": st.column_config.NumberColumn("목표가", help="이 가격 이상 도달 시 알림"),
            "손절가": st.column_config.NumberColumn("손절가", help="이 가격 이하 이탈 시 알림"),
            "신호알림": st.column_config.CheckboxColumn("신호변화 알림"),
        },
        key="alerts_editor",
    )
    if st.button("💾 알림 설정 저장", type="primary"):
        cfg = {}
        for _, r in edited.iterrows():
            key = f"{str(r['심볼']).strip()}|{str(r['시장']).strip().upper()}"
            entry = {"signal_alert": bool(r["신호알림"])}
            if pd.notna(r["목표가"]):
                entry["target"] = float(r["목표가"])
            if pd.notna(r["손절가"]):
                entry["stop"] = float(r["손절가"])
            cfg[key] = entry
        save_json(ALERTS_FILE, cfg)
        st.success("저장 완료!")

    if monitored == {}:
        st.info("워치리스트나 보유종목을 먼저 추가하면 여기 나타납니다.")

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
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06,
        row_heights=[0.68, 0.32],
        subplot_titles=("자산곡선 — 신호 전략 vs 그냥 보유 (시작=100)", "종합 신호 점수"),
    )
    fig.add_trace(go.Scatter(x=dates, y=res["equity"] * 100, name="신호 전략",
                             line=dict(color="#2563EB", width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=dates, y=res["price"] * 100, name="그냥 보유(Buy&Hold)",
                             line=dict(color="#9CA3AF", width=1.6, dash="dot")), row=1, col=1)
    fig.add_hline(y=100, line_dash="dot", line_color="#D1D5DB", row=1, col=1)

    fig.add_trace(go.Scatter(x=dates, y=res["signal"], name="종합 신호",
                             line=dict(color="#8e44ad", width=1.2)), row=2, col=1)
    fig.add_hline(y=p["buy_th"], line_dash="dash", line_color="rgba(229,57,53,0.6)",
                  annotation_text=f"매수 {p['buy_th']:.0f}", annotation_position="right", row=2, col=1)
    fig.add_hline(y=p["sell_th"], line_dash="dash", line_color="rgba(37,99,235,0.6)",
                  annotation_text=f"청산 {p['sell_th']:.0f}", annotation_position="right", row=2, col=1)
    fig.update_layout(
        height=560, hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="right", x=1),
        margin=dict(l=10, r=70, t=60, b=10),
    )
    return fig


def page_backtest():
    st.title("백테스트 — 신호대로 매매했다면?")
    st.caption("이 대시보드의 종합 신호대로 과거에 매매했다면 수익률이 어땠을지 검증합니다. "
               "신호의 신뢰도를 가늠하는 참고용이며, 과거 성과가 미래를 보장하지 않습니다.")

    symbol, market, dispname = symbol_picker("bt")

    c1, c2, c3, c4 = st.columns([1.3, 1, 1, 1])
    with c1:
        period_label = st.selectbox("검증 기간", ["1년", "2년", "5년"], index=1)
        period = {"1년": "1y", "2년": "2y", "5년": "5y"}[period_label]
    with c2:
        buy_th = st.slider("매수 기준", 50, 80, 60, step=5,
                           help="종합 신호 점수가 이 값 이상이면 매수 진입")
    with c3:
        sell_th = st.slider("청산 기준", 30, 50, 45, step=5,
                            help="종합 신호 점수가 이 값 이하이면 청산")
    with c4:
        fee = st.slider("거래비용(편도 %)", 0.0, 0.5, 0.1, step=0.05,
                        help="수수료+슬리피지 가정. 진입·청산마다 차감")

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
            f'<div class="lbl">신호 전략 수익률</div>'
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

    verdict = (f"신호 전략이 그냥 보유보다 <b>{diff:+.1f}%p</b> "
               f"{'앞섰습니다 👍' if won else '뒤졌습니다'}.")
    sub = ("이 종목·기간에선 신호 매매가 더 나았어요. 다만 표본이 한정적이라 맹신은 금물."
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

    st.subheader("메뉴 7개")
    st.markdown(
        _guide_card("📊 기술적 분석",
                    "한 종목을 깊게 분석. 결론 3카드 → 차트(이동평균·일목·지지저항) → 지표 요약 → "
                    "종합 총평(추세·모멘텀·진입리스크) → 전문가 목표가 괴리율 → 지지/저항 → "
                    "긍정·부정 신호 → 관련 뉴스. <b>이 앱의 핵심 화면</b>이에요.", "#2563EB")
        + _guide_card("🔭 스캐너",
                      "워치리스트와 보유 종목의 종합 신호를 <b>한 번에 계산해 강한 순으로 랭킹</b>해요. "
                      "‘상승 우세만’ 필터로 지금 주목할 종목을 빠르게 추려볼 수 있어요.", "#7C3AED")
        + _guide_card("🧪 백테스트",
                      "‘이 신호대로 과거에 매매했다면?’을 검증해요. <b>신호 전략 vs 그냥 보유</b> 수익률을 "
                      "비교하고 거래 횟수·승률·최대낙폭을 보여줘 <b>신호의 신뢰도</b>를 가늠하게 해줘요. "
                      "과거 성과가 미래를 보장하진 않아요.", "#0891B2")
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
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.sidebar.title("📈 자산 대시보드")

    # 사용 가이드 버튼 (누르면 가이드 페이지로 이동)
    if st.sidebar.button("📖 사용 가이드", use_container_width=True):
        st.session_state["show_guide"] = True

    page = st.sidebar.radio(
        "메뉴", ["기술적 분석", "스캐너", "백테스트", "시장 개요", "내 자산", "워치리스트", "알림 설정"],
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
    elif page == "백테스트":
        page_backtest()
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
