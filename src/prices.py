"""
가격 데이터 수집 모듈.

시장 구분(market):
  - "KR"   : 한국 주식. 6자리 코드 (예: 005930) -> yfinance .KS/.KQ 자동 시도
  - "US"   : 미국 주식. 티커 그대로 (예: AAPL)
  - "COIN" : 암호화폐. 심볼 (예: BTC) -> 업비트 KRW 마켓 (KRW-BTC)

반환 OHLCV DataFrame은 소문자 컬럼(open/high/low/close/volume)과
DatetimeIndex 로 정규화된다. (지표 모듈이 소문자 컬럼을 기대)
"""
from __future__ import annotations

import pandas as pd
import requests
import yfinance as yf

UPBIT_BASE = "https://api.upbit.com/v1"
_TIMEOUT = 10


# ---------------------------------------------------------------------------
# 공통 정규화
# ---------------------------------------------------------------------------
def _normalize_yf(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    keep = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    df = df[keep].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df.dropna(subset=["close"])


# ---------------------------------------------------------------------------
# 한국 주식
# ---------------------------------------------------------------------------
def _kr_candidates(code: str) -> list[str]:
    code = code.strip().upper()
    if code.endswith((".KS", ".KQ")):
        return [code]
    return [f"{code}.KS", f"{code}.KQ"]  # 코스피 우선, 실패 시 코스닥


# ---------------------------------------------------------------------------
# 암호화폐 (업비트)
# ---------------------------------------------------------------------------
def _coin_market(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if symbol.startswith("KRW-"):
        return symbol
    return f"KRW-{symbol}"


def _upbit_ohlcv(symbol: str, count: int = 200, unit: str = "days") -> pd.DataFrame:
    market = _coin_market(symbol)
    url = f"{UPBIT_BASE}/candles/{unit}"  # days / weeks / months
    resp = requests.get(
        url, params={"market": market, "count": min(count, 200)}, timeout=_TIMEOUT
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list) or not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["candle_date_time_kst"])
    df = df.rename(
        columns={
            "opening_price": "open",
            "high_price": "high",
            "low_price": "low",
            "trade_price": "close",
            "candle_acc_trade_volume": "volume",
        }
    )
    df = df[["date", "open", "high", "low", "close", "volume"]].set_index("date")
    return df.sort_index()  # 업비트는 최신순 -> 오래된순 정렬


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------
def get_ohlcv(symbol: str, market: str, period: str = "1y", timeframe: str = "D") -> pd.DataFrame:
    """시장별 OHLCV 수집. timeframe: D(일봉)/W(주봉)/M(월봉). 실패 시 빈 DataFrame."""
    market = market.upper()
    tf = str(timeframe).upper()
    try:
        if market == "COIN":
            unit = {"D": "days", "W": "weeks", "M": "months"}.get(tf, "days")
            return _upbit_ohlcv(symbol, count=200, unit=unit)
        interval = {"D": "1d", "W": "1wk", "M": "1mo"}.get(tf, "1d")
        # 주/월봉은 더 긴 기간이 필요
        per = period if tf == "D" else ("5y" if tf == "W" else "max")
        tickers = _kr_candidates(symbol) if market == "KR" else [symbol.strip().upper()]
        for cand in tickers:
            df = _normalize_yf(
                yf.Ticker(cand).history(period=per, interval=interval, auto_adjust=True)
            )
            if not df.empty:
                return df
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def get_current_price(symbol: str, market: str) -> float | None:
    """현재가(종가 기준 최신). 실패 시 None."""
    market = market.upper()
    try:
        if market == "COIN":
            resp = requests.get(
                f"{UPBIT_BASE}/ticker",
                params={"markets": _coin_market(symbol)},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            if data:
                return float(data[0]["trade_price"])
            return None
        df = get_ohlcv(symbol, market, period="5d")
        if df.empty:
            return None
        return float(df["close"].iloc[-1])
    except Exception:
        return None


def get_fx_usdkrw() -> float | None:
    """원/달러 환율 (미국 주식을 원화로 환산할 때 사용)."""
    try:
        df = _normalize_yf(yf.Ticker("USDKRW=X").history(period="5d"))
        if df.empty:
            return None
        return float(df["close"].iloc[-1])
    except Exception:
        return None


def currency_of(market: str) -> str:
    return "USD" if market.upper() == "US" else "KRW"


def get_quote(symbol: str, market: str) -> dict:
    """검색결과 비교용 간단 시세: {price, market_cap, value_24h(거래대금)}."""
    market = market.upper()
    try:
        if market == "COIN":
            resp = requests.get(
                f"{UPBIT_BASE}/ticker", params={"markets": _coin_market(symbol)},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            d = resp.json()[0]
            return {
                "price": float(d["trade_price"]),
                "market_cap": None,
                "value_24h": float(d.get("acc_trade_price_24h") or 0),
            }
        tickers = _kr_candidates(symbol) if market == "KR" else [symbol.strip().upper()]
        for tk in tickers:
            try:
                fi = yf.Ticker(tk).fast_info
                price = fi.get("last_price") or fi.get("lastPrice")
                vol = fi.get("last_volume") or fi.get("lastVolume")
                cap = fi.get("market_cap") or fi.get("marketCap")
            except Exception:
                continue
            if price:
                value = float(price) * float(vol) if vol else None
                return {"price": float(price), "market_cap": cap, "value_24h": value}
    except Exception:
        pass
    return {"price": None, "market_cap": None, "value_24h": None}


def get_fundamentals(symbol: str, market: str) -> dict:
    """
    종목 기본 지표. 실패하거나 코인이면 빈 dict.
    반환 키: per, pbr, market_cap, dividend_yield, week52_high, week52_low, week52_pos(0~1)
    """
    market = market.upper()
    if market == "COIN":
        return {}
    tickers = _kr_candidates(symbol) if market == "KR" else [symbol.strip().upper()]
    for tk in tickers:
        try:
            info = yf.Ticker(tk).get_info()
        except Exception:
            continue
        if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None \
                and info.get("fiftyTwoWeekHigh") is None:
            continue
        hi = info.get("fiftyTwoWeekHigh")
        lo = info.get("fiftyTwoWeekLow")
        cur = info.get("currentPrice") or info.get("regularMarketPrice")
        pos = None
        if hi and lo and cur and hi != lo:
            pos = max(0.0, min(1.0, (cur - lo) / (hi - lo)))
        target_mean = info.get("targetMeanPrice")
        upside = None
        if target_mean and cur:
            upside = (target_mean - cur) / cur * 100
        return {
            "per": info.get("trailingPE"),
            "pbr": info.get("priceToBook"),
            "market_cap": info.get("marketCap"),
            "dividend_yield": info.get("dividendYield"),
            "week52_high": hi,
            "week52_low": lo,
            "week52_pos": pos,
            "current": cur,
            # 전문가(애널리스트) 의견
            "rec_key": info.get("recommendationKey"),
            "rec_mean": info.get("recommendationMean"),
            "analyst_count": info.get("numberOfAnalystOpinions"),
            "target_mean": target_mean,
            "target_high": info.get("targetHighPrice"),
            "target_low": info.get("targetLowPrice"),
            "target_upside": upside,
        }
    return {}
