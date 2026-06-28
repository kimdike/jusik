"""
시장 개요(거시 흐름).

  - 주요 지수 등락률 (코스피/코스닥/S&P500/나스닥/USD-KRW/VIX)
  - 코인 공포탐욕지수 (alternative.me, 무료)
  - 거시 뉴스 (news 모듈)
"""
from __future__ import annotations

import requests
import yfinance as yf

from . import news

_TIMEOUT = 8

INDICES = [
    ("코스피", "^KS11"),
    ("코스닥", "^KQ11"),
    ("S&P 500", "^GSPC"),
    ("나스닥", "^IXIC"),
    ("USD/KRW", "KRW=X"),
    ("VIX(변동성)", "^VIX"),
]


def get_indices() -> list[dict]:
    """각 지수의 현재값과 전일 대비 등락률."""
    out = []
    for name, sym in INDICES:
        try:
            hist = yf.Ticker(sym).history(period="5d")
            closes = hist["Close"].dropna()
            if len(closes) >= 2:
                last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
                chg = (last - prev) / prev * 100 if prev else 0.0
                out.append({"name": name, "symbol": sym, "value": last, "change_pct": round(chg, 2)})
            elif len(closes) == 1:
                out.append({"name": name, "symbol": sym, "value": float(closes.iloc[-1]), "change_pct": None})
        except Exception:
            out.append({"name": name, "symbol": sym, "value": None, "change_pct": None})
    return out


def get_fear_greed_crypto() -> dict | None:
    """코인 공포탐욕지수 (0~100, 0=극단적 공포)."""
    try:
        r = requests.get("https://api.alternative.me/fng/", params={"limit": 1}, timeout=_TIMEOUT).json()
        d = r["data"][0]
        ko = {
            "Extreme Fear": "극단적 공포", "Fear": "공포", "Neutral": "중립",
            "Greed": "탐욕", "Extreme Greed": "극단적 탐욕",
        }
        cls = d.get("value_classification", "")
        return {"value": int(d["value"]), "label": ko.get(cls, cls)}
    except Exception:
        return None


def get_macro_news(limit: int = 8) -> list[dict]:
    """증시 거시 뉴스."""
    return news.get_news("증시 경제", region="KR", limit=limit)
