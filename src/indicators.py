"""
기술적 지표 계산 모듈.

모든 함수는 OHLCV 컬럼(open, high, low, close, volume)을 가진
pandas DataFrame을 입력으로 받습니다. 외부 TA 라이브러리 없이
pandas / numpy 만으로 구현했습니다 (의존성 최소화 + 동작 투명성).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# 이동평균
# ---------------------------------------------------------------------------
def sma(series: pd.Series, window: int) -> pd.Series:
    """단순이동평균(Simple Moving Average)."""
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    """지수이동평균(Exponential Moving Average)."""
    return series.ewm(span=window, adjust=False).mean()


# ---------------------------------------------------------------------------
# RSI (상대강도지수)
# ---------------------------------------------------------------------------
def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """RSI. 70 이상 과매수, 30 이하 과매도로 통상 해석."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # Wilder smoothing (EMA with alpha = 1/window)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    # avg_loss == 0 이면 RSI = 100
    out = out.where(avg_loss != 0, 100.0)
    return out


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------
def macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """MACD line, signal line, histogram 반환."""
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return pd.DataFrame(
        {"macd": macd_line, "signal": signal_line, "hist": hist}
    )


# ---------------------------------------------------------------------------
# 볼린저 밴드
# ---------------------------------------------------------------------------
def bollinger(series: pd.Series, window: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    """볼린저 밴드: 중심선(SMA), 상단, 하단, %B."""
    mid = sma(series, window)
    std = series.rolling(window=window, min_periods=window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    pct_b = (series - lower) / (upper - lower)
    return pd.DataFrame(
        {"mid": mid, "upper": upper, "lower": lower, "pct_b": pct_b}
    )


# ---------------------------------------------------------------------------
# 스토캐스틱
# ---------------------------------------------------------------------------
def stochastic(
    df: pd.DataFrame, k: int = 14, d: int = 3, smooth_k: int = 3
) -> pd.DataFrame:
    """스토캐스틱 %K, %D."""
    low_min = df["low"].rolling(window=k, min_periods=k).min()
    high_max = df["high"].rolling(window=k, min_periods=k).max()
    raw_k = 100 * (df["close"] - low_min) / (high_max - low_min)
    k_line = raw_k.rolling(window=smooth_k, min_periods=smooth_k).mean()
    d_line = k_line.rolling(window=d, min_periods=d).mean()
    return pd.DataFrame({"k": k_line, "d": d_line})


# ---------------------------------------------------------------------------
# 일목균형표 (Ichimoku)
# ---------------------------------------------------------------------------
def ichimoku(
    df: pd.DataFrame,
    tenkan: int = 9,
    kijun: int = 26,
    senkou_b: int = 52,
) -> pd.DataFrame:
    """
    일목균형표 5개 선.
    - tenkan_sen (전환선)
    - kijun_sen (기준선)
    - senkou_a (선행스팬1) : kijun 만큼 미래로 이동
    - senkou_b (선행스팬2) : kijun 만큼 미래로 이동
    - chikou (후행스팬) : kijun 만큼 과거로 이동
    """
    high, low, close = df["high"], df["low"], df["close"]

    def mid(period: int) -> pd.Series:
        return (
            high.rolling(period, min_periods=period).max()
            + low.rolling(period, min_periods=period).min()
        ) / 2

    tenkan_sen = mid(tenkan)
    kijun_sen = mid(kijun)
    senkou_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun)
    senkou_b_line = mid(senkou_b).shift(kijun)
    chikou = close.shift(-kijun)

    return pd.DataFrame(
        {
            "tenkan": tenkan_sen,
            "kijun": kijun_sen,
            "senkou_a": senkou_a,
            "senkou_b": senkou_b_line,
            "chikou": chikou,
        }
    )


# ---------------------------------------------------------------------------
# 피보나치 되돌림
# ---------------------------------------------------------------------------
def fibonacci_levels(df: pd.DataFrame, lookback: int = 120) -> dict:
    """
    최근 lookback 봉에서의 스윙 고점/저점 기준 피보나치 되돌림 레벨.
    상승추세(저점->고점)를 가정해 0%(고점) ~ 100%(저점) 레벨 산출.
    """
    window = df.tail(lookback)
    if window.empty:
        return {}
    swing_high = float(window["high"].max())
    swing_low = float(window["low"].min())
    diff = swing_high - swing_low
    ratios = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
    levels = {f"{int(r * 100)}%": swing_high - diff * r for r in ratios}
    return {
        "high": swing_high,
        "low": swing_low,
        "levels": levels,
    }


# ---------------------------------------------------------------------------
# ADX (추세 강도)
# ---------------------------------------------------------------------------
def adx(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """ADX 및 +DI, -DI. ADX 25 이상이면 추세가 강하다고 해석."""
    high, low, close = df["high"], df["low"], df["close"]
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)

    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)

    atr = tr.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / window, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / window, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_line = dx.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()

    return pd.DataFrame({"adx": adx_line, "plus_di": plus_di, "minus_di": minus_di})


# ---------------------------------------------------------------------------
# 추세선 (선형회귀 기울기)
# ---------------------------------------------------------------------------
def trend_slope(series: pd.Series, lookback: int = 20) -> float:
    """
    최근 lookback 봉의 종가에 선형회귀를 적용해 기울기를 반환.
    가격 대비 정규화한 1봉당 변화율(%)로 환산해 비교 가능하게 만든다.
    """
    y = series.dropna().tail(lookback).to_numpy(dtype=float)
    if len(y) < 3:
        return 0.0
    x = np.arange(len(y), dtype=float)
    slope = np.polyfit(x, y, 1)[0]
    avg = y.mean()
    if avg == 0:
        return 0.0
    return float(slope / avg * 100)  # 1봉당 평균가격 대비 % 변화


# ---------------------------------------------------------------------------
# 한 번에 전부 계산
# ---------------------------------------------------------------------------
def compute_all(df: pd.DataFrame) -> dict:
    """
    OHLCV DataFrame을 받아 모든 지표를 계산해 dict로 반환.
    app / signals 에서 공통으로 사용.
    """
    close = df["close"]
    out: dict = {}
    out["sma20"] = sma(close, 20)
    out["sma60"] = sma(close, 60)
    out["sma120"] = sma(close, 120)
    out["ema20"] = ema(close, 20)
    out["rsi"] = rsi(close, 14)
    out["macd"] = macd(close)
    out["bollinger"] = bollinger(close)
    out["stochastic"] = stochastic(df)
    out["ichimoku"] = ichimoku(df)
    out["adx"] = adx(df)
    out["fibonacci"] = fibonacci_levels(df)
    out["trend_slope"] = trend_slope(close, 20)
    return out
