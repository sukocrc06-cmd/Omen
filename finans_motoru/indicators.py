"""
indicators.py
--------------
Teknik indikatörlerin sıfırdan (harici TA kütüphanesine bağımlı olmadan)
pandas / numpy ile implementasyonu.

Tüm fonksiyonlar bir pandas.DataFrame (kolonlar: open, high, low, close, volume)
alır ve DataFrame'e yeni kolonlar ekleyerek döndürür ya da bir pandas.Series
döndürür. Bu şekilde zincirleme (chaining) kullanım kolaylaşır.
"""

from __future__ import annotations
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Trend indikatörleri
# ---------------------------------------------------------------------------

def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(window=length, min_periods=length).mean()


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False, min_periods=length).mean()


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def adx(df: pd.DataFrame, length: int = 14) -> pd.Series:
    """Average Directional Index - trend gücünü ölçer (0-100)."""
    high, low, close = df["high"], df["low"], df["close"]

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = true_range(df)
    atr_val = tr.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()

    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(
        alpha=1 / length, min_periods=length, adjust=False
    ).mean() / atr_val
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(
        alpha=1 / length, min_periods=length, adjust=False
    ).mean() / atr_val

    dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100
    adx_val = dx.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    return adx_val


# ---------------------------------------------------------------------------
# Momentum indikatörleri
# ---------------------------------------------------------------------------

def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_val = 100 - (100 / (1 + rs))
    rsi_val = rsi_val.fillna(50)
    return rsi_val


def stochastic(df: pd.DataFrame, k_length: int = 14, d_length: int = 3, smooth: int = 3):
    low_min = df["low"].rolling(window=k_length, min_periods=k_length).min()
    high_max = df["high"].rolling(window=k_length, min_periods=k_length).max()

    raw_k = 100 * (df["close"] - low_min) / (high_max - low_min).replace(0, np.nan)
    k = raw_k.rolling(window=smooth, min_periods=smooth).mean()
    d = k.rolling(window=d_length, min_periods=d_length).mean()
    return k, d


# ---------------------------------------------------------------------------
# Volatilite indikatörleri
# ---------------------------------------------------------------------------

def true_range(df: pd.DataFrame) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr


def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    tr = true_range(df)
    return tr.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()


def bollinger_bands(series: pd.Series, length: int = 20, num_std: float = 2.0):
    mid = sma(series, length)
    std = series.rolling(window=length, min_periods=length).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, mid, lower


# ---------------------------------------------------------------------------
# Hacim indikatörleri
# ---------------------------------------------------------------------------

def volume_sma(volume: pd.Series, length: int = 20) -> pd.Series:
    return volume.rolling(window=length, min_periods=length).mean()


def obv(df: pd.DataFrame) -> pd.Series:
    """On Balance Volume."""
    direction = np.sign(df["close"].diff()).fillna(0)
    return (direction * df["volume"]).cumsum()


# ---------------------------------------------------------------------------
# Üst zaman dilimi (higher-timeframe) trend teyidi
# ---------------------------------------------------------------------------

def higher_tf_trend(df: pd.DataFrame, rule: str, ema_len: int = 50) -> pd.Series:
    """
    Kapanış fiyatını daha büyük bir zaman dilimine (rule, ör. '1D', '4h')
    yeniden örnekleyip o zaman diliminde EMA'ya göre trend yönünü (+1/-1)
    hesaplar ve orijinal (düşük zaman dilimi) index'e geri hizalar.

    Look-ahead sızıntısını önlemek için: bir üst zaman dilimi barı ancak
    KAPANDIKTAN sonra bilinir. Bu yüzden trend bir üst-TF bar geriye
    kaydırılır (shift(1)) ve ancak öyle düşük zaman dilimine forward-fill
    edilir - yani bir bar şu an içinde bulunduğu üst-TF barın değil, bir
    önceki TAMAMLANMIŞ üst-TF barın trendini görür.
    """
    htf_close = df["close"].resample(rule, label="right", closed="right").last().dropna()
    if len(htf_close) < ema_len + 2:
        return pd.Series(np.nan, index=df.index)
    htf_ema = ema(htf_close, ema_len)
    htf_trend = np.sign(htf_close - htf_ema).shift(1)
    return htf_trend.reindex(df.index, method="ffill")


# ---------------------------------------------------------------------------
# Ana fonksiyon: tüm indikatörleri tek seferde hesapla
# ---------------------------------------------------------------------------

def add_all_indicators(df: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    """
    df: en az open, high, low, close, volume kolonlarını içeren DataFrame.
    cfg: indikatör parametrelerini özelleştirmek için opsiyonel sözlük.
    """
    cfg = cfg or {}
    out = df.copy()

    out["ema_fast"] = ema(out["close"], cfg.get("ema_fast", 9))
    out["ema_slow"] = ema(out["close"], cfg.get("ema_slow", 21))
    out["ema_trend"] = ema(out["close"], cfg.get("ema_trend", 50))

    out["rsi"] = rsi(out["close"], cfg.get("rsi_len", 14))

    macd_line, signal_line, hist = macd(
        out["close"],
        cfg.get("macd_fast", 12),
        cfg.get("macd_slow", 26),
        cfg.get("macd_signal", 9),
    )
    out["macd"] = macd_line
    out["macd_signal"] = signal_line
    out["macd_hist"] = hist

    upper, mid, lower = bollinger_bands(
        out["close"], cfg.get("bb_len", 20), cfg.get("bb_std", 2.0)
    )
    out["bb_upper"] = upper
    out["bb_mid"] = mid
    out["bb_lower"] = lower

    k, d = stochastic(
        out, cfg.get("stoch_k", 14), cfg.get("stoch_d", 3), cfg.get("stoch_smooth", 3)
    )
    out["stoch_k"] = k
    out["stoch_d"] = d

    out["atr"] = atr(out, cfg.get("atr_len", 14))
    out["adx"] = adx(out, cfg.get("adx_len", 14))
    out["vol_sma"] = volume_sma(out["volume"], cfg.get("vol_len", 20))
    out["obv"] = obv(out)

    return out
