"""
차트 이미지(PNG) 생성.

가격선 + 이동평균 위에 현재가·지지선·저항선(목표가 후보)·전문가 목표가·
사용자 목표가 선을 그어 한 장의 이미지로 만든다. 텔레그램 발송이나
대시보드 다운로드에 사용.

matplotlib(Agg 백엔드) 사용 — 서버/헤드리스에서 동작. 한글은 맑은고딕.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

from . import indicators as ind  # noqa: E402
from . import levels as lv  # noqa: E402
from . import prices, signals  # noqa: E402

# 한글 폰트 (Windows 맑은고딕 우선, 없으면 기본 폰트)
for _fp in (r"C:\Windows\Fonts\malgun.ttf", "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"):
    if Path(_fp).exists():
        try:
            font_manager.fontManager.addfont(_fp)
            plt.rcParams["font.family"] = font_manager.FontProperties(fname=_fp).get_name()
            break
        except Exception:
            pass
plt.rcParams["axes.unicode_minus"] = False


def _fmt(v, is_us: bool) -> str:
    if v is None:
        return "-"
    return f"${v:,.2f}" if is_us else f"{v:,.0f}원"


def render_chart(
    symbol: str,
    market: str,
    name: str,
    out_path: str,
    period: str = "6mo",
    target: float | None = None,
    entry: float | None = None,
    analyst_target: float | None = None,
    df=None,
) -> str | None:
    """종목 차트 이미지를 out_path(PNG)로 저장. 성공 시 경로, 실패 시 None.
    df를 넘기면 재조회 없이 그대로 사용(알림 등에서 중복 조회 방지)."""
    if df is None:
        df = prices.get_ohlcv(symbol, market, period)
    if df is None or df.empty:
        return None
    is_us = market.upper() == "US"
    all_ind = ind.compute_all(df)
    levels = lv.compute_levels(df, all_ind)
    res = signals.evaluate(df)
    cur = float(df["close"].iloc[-1])

    def fp(v):
        return _fmt(v, is_us)

    fig, ax = plt.subplots(figsize=(10, 6), dpi=130)
    ax.plot(df.index, df["close"], color="#111827", lw=1.5, label="종가")
    if all_ind.get("sma20") is not None:
        ax.plot(df.index, all_ind["sma20"], color="#f39c12", lw=1.0, label="20일선")
    if all_ind.get("sma60") is not None:
        ax.plot(df.index, all_ind["sma60"], color="#16a085", lw=1.0, label="60일선")

    x_left, x_right = df.index[0], df.index[-1]

    def _short(lbl: str, n: int = 24) -> str:
        return lbl if len(lbl) <= n else lbl[: n - 1] + "…"

    _lblbox = dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.6)

    # 너무 가까운(라벨 겹침) 레벨은 선만 긋고 글자는 생략
    def _draw_levels(items, color, txtcolor, prefix, va):
        labeled = []
        for it in items:
            ax.axhline(it["price"], color=color, lw=1.0, ls="--", alpha=0.85)
            if any(abs(it["price"] - y) / cur < 0.02 for y in labeled):
                continue  # 이미 라벨 단 선과 2% 이내 → 글자 생략(겹침 방지)
            sign = "+" if it["dist_pct"] >= 0 else ""
            ax.text(x_left, it["price"],
                    f" {prefix} {fp(it['price'])} ({sign}{it['dist_pct']:.1f}%) · {_short(it['label'])}",
                    color=txtcolor, va=va, fontsize=8, bbox=_lblbox)
            labeled.append(it["price"])

    _draw_levels((levels.get("resistances") or [])[:3], "#e74c3c", "#c0392b", "저항", "bottom")
    _draw_levels((levels.get("supports") or [])[:3], "#2980b9", "#1f6391", "지지", "top")

    # 전문가 평균 목표가 (보라 점선)
    if analyst_target:
        ax.axhline(analyst_target, color="#8e44ad", lw=1.2, ls=":")
        ax.text(x_left, analyst_target, f"전문가 목표 {fp(analyst_target)}",
                color="#8e44ad", va="bottom", fontsize=8.5, fontweight="bold")

    # 현재가 (파란 실선)
    ax.axhline(cur, color="#2563EB", lw=1.4)
    ax.text(x_right, cur, f"  현재가 {fp(cur)}", color="#2563EB",
            va="center", fontsize=9.5, fontweight="bold")

    # 사용자 목표가 (초록 실선)
    if target:
        gap = (target - cur) / cur * 100 if cur else 0
        ax.axhline(target, color="#16A34A", lw=1.8)
        ax.text(x_right, target, f"  목표가 {fp(target)} ({gap:+.1f}%)", color="#16A34A",
                va="center", fontsize=9.5, fontweight="bold")

    # 사용자 진입가 = 매수 자리 (청록 실선)
    if entry:
        gap = (entry - cur) / cur * 100 if cur else 0
        ax.axhline(entry, color="#0891B2", lw=1.8)
        ax.text(x_right, entry, f"  매수자리 {fp(entry)} ({gap:+.1f}%)", color="#0891B2",
                va="center", fontsize=9.5, fontweight="bold")

    up = res.get("up_pct")
    head = f"{name} ({symbol}) · {fp(cur)}"
    if up is not None:
        head += f" · 신호 {up:.0f}/100"
    ax.set_title(head + ("\n" + res.get("verdict", "") if res.get("verdict") else ""),
                 fontsize=12, fontweight="bold")
    ax.legend(loc="upper right", fontsize=8, framealpha=0.9)
    ax.grid(alpha=0.18)
    ax.margins(x=0.16)
    ax.tick_params(labelsize=8)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return out_path
