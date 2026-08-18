"""
signal_engine.py
-----------------
Birden fazla indikatörü ağırlıklı bir puanlama sistemiyle birleştirip
her mum (bar) için bir "skor" (-1..+1 arası) ve bu skordan türetilen
AL / SAT / BEKLE etiketi + güven yüzdesi üretir.

ÖNEMLİ: Bu sistem kesin bir "doğru" sinyal garanti etmez; sadece seçilen
indikatörlerin birlikte söylediklerini ağırlıklı biçimde özetler. Amaç,
tek bir indikatöre körü körüne güvenmek yerine, çoklu-doğrulama (confluence)
mantığıyla daha sağlam bir karar desteği sunmaktır.
"""

from __future__ import annotations
import numpy as np
import pandas as pd

from indicators import add_all_indicators


DEFAULT_WEIGHTS = {
    "ema_cross": 1.2,      # kısa/uzun EMA kesişimi (trend yönü)
    "trend_filter": 0.8,   # fiyat vs EMA50 (ana trend filtresi)
    "macd": 1.0,           # MACD histogram yönü
    "rsi": 1.0,            # RSI aşırı alım/satım + orta çizgi
    "bollinger": 0.7,      # fiyatın bantlara göre konumu
    "stochastic": 0.7,     # stokastik kesişim + bölge
    "volume": 0.6,         # hacim teyidi
}


def _score_ema_cross(df: pd.DataFrame) -> pd.Series:
    diff = df["ema_fast"] - df["ema_slow"]
    prev_diff = diff.shift(1)
    score = np.sign(diff)
    # Yeni kesişim anlarında sinyali güçlendir
    cross_up = (prev_diff <= 0) & (diff > 0)
    cross_down = (prev_diff >= 0) & (diff < 0)
    score = score.where(~cross_up, 1.5)
    score = score.where(~cross_down, -1.5)
    return score.clip(-1.5, 1.5) / 1.5


def _score_trend_filter(df: pd.DataFrame) -> pd.Series:
    return np.sign(df["close"] - df["ema_trend"])


def _score_macd(df: pd.DataFrame) -> pd.Series:
    hist = df["macd_hist"]
    prev = hist.shift(1)
    base = np.sign(hist)
    momentum_up = (hist > prev)
    # histogram pozitif ve büyüyorsa güçlü al, negatif ve küçülüyorsa güçlü sat
    score = base.copy()
    score = score.where(~((base > 0) & momentum_up), 1.0)
    score = score.where(~((base < 0) & ~momentum_up), -1.0)
    return score


def _score_rsi(df: pd.DataFrame) -> pd.Series:
    r = df["rsi"]
    score = pd.Series(0.0, index=df.index)
    score = score.mask(r < 30, 1.0)     # aşırı satım -> al eğilimi
    score = score.mask(r > 70, -1.0)    # aşırı alım -> sat eğilimi
    score = score.mask((r >= 45) & (r <= 55), 0.0)
    mid_bull = (r > 55) & (r <= 70)
    mid_bear = (r >= 30) & (r < 45)
    score = score.mask(mid_bull, 0.4)
    score = score.mask(mid_bear, -0.4)
    return score


def _score_bollinger(df: pd.DataFrame) -> pd.Series:
    width = (df["bb_upper"] - df["bb_lower"]).replace(0, np.nan)
    pos = (df["close"] - df["bb_mid"]) / (width / 2)
    # fiyat alt banda yakın/altında -> al eğilimi, üst banda yakın/üstünde -> sat eğilimi
    score = -pos.clip(-1.5, 1.5) / 1.5
    return score


def _score_stochastic(df: pd.DataFrame) -> pd.Series:
    k, d = df["stoch_k"], df["stoch_d"]
    prev_diff = (k.shift(1) - d.shift(1))
    diff = k - d
    cross_up = (prev_diff <= 0) & (diff > 0) & (k < 50)
    cross_down = (prev_diff >= 0) & (diff < 0) & (k > 50)
    score = pd.Series(0.0, index=df.index)
    score = score.mask(cross_up, 1.0)
    score = score.mask(cross_down, -1.0)
    score = score.mask(k < 20, score + 0.5)
    score = score.mask(k > 80, score - 0.5)
    return score.clip(-1.5, 1.5) / 1.5


def _score_volume(df: pd.DataFrame) -> pd.Series:
    ratio = (df["volume"] / df["vol_sma"]).replace([np.inf, -np.inf], np.nan)
    # yüksek hacim, mevcut fiyat hareketinin yönünü teyit eder (çarpan gibi davranır)
    direction = np.sign(df["close"].diff())
    confirm = (ratio > 1.2).astype(float)
    return (direction * confirm).fillna(0.0)


def compute_signals(df: pd.DataFrame, cfg: dict | None = None, weights: dict | None = None,
                     buy_th: float = 0.30, sell_th: float = -0.30, strong_th: float = 0.60) -> pd.DataFrame:
    """
    df: OHLCV DataFrame (open, high, low, close, volume).
    buy_th/sell_th/strong_th: sinyal eşikleri (bkz. _hysteresis_labels). optimize.py
        tarafından zaman aralığına özel ayarlanabilir hale getirmek için parametrelendirildi.
    Dönüş: indikatörler + 'score' (-1..1), 'signal' (AL/SAT/BEKLE), 'confidence' (0-100).
    """
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    out = add_all_indicators(df, cfg)

    components = {
        "ema_cross": _score_ema_cross(out),
        "trend_filter": _score_trend_filter(out),
        "macd": _score_macd(out),
        "rsi": _score_rsi(out),
        "bollinger": _score_bollinger(out),
        "stochastic": _score_stochastic(out),
        "volume": _score_volume(out),
    }

    total_weight = sum(weights.values())
    weighted_sum = sum(components[k].fillna(0) * weights[k] for k in components)
    score = (weighted_sum / total_weight).clip(-1, 1)

    # Ham skoru kısa bir hareketli ortalamayla yumuşat (tek bar'lık gürültüyü azaltır)
    smooth_score = score.rolling(window=3, min_periods=1).mean()
    out["score"] = smooth_score
    out["score_raw"] = score
    for name, series in components.items():
        out[f"cmp_{name}"] = series

    # kaç indikatör aynı yönde hemfikir (confluence) -> güven skoru
    signs = pd.concat([np.sign(components[k].fillna(0)) for k in components], axis=1)
    agree_ratio = signs.apply(
        lambda row: max((row == 1).sum(), (row == -1).sum()) / len(row), axis=1
    )
    out["confidence"] = (agree_ratio * out["score"].abs().clip(0, 1) * 100).round(1)

    out["signal"] = _hysteresis_labels(out["score"], buy_th=buy_th, sell_th=sell_th, strong_th=strong_th)

    return out


def _hysteresis_labels(score: pd.Series, buy_th: float = 0.30, sell_th: float = -0.30,
                        strong_th: float = 0.60) -> list:
    """
    Skor eşiği aşıldığında yön değiştirir ve OPPOSITE eşik aşılana kadar o yönde
    kalır (histerezis). Bu, skorun eşik etrafında salınıp AL/SAT arasında sürekli
    gidip gelmesini (whipsaw) engelleyip daha az ama daha anlamlı sinyal üretir.
    """
    labels = []
    state = 0  # -1: SAT eğilimi, 0: nötr, 1: AL eğilimi
    for s in score:
        if pd.isna(s):
            labels.append("BEKLE")
            continue
        if state != 1 and s >= buy_th:
            state = 1
        elif state != -1 and s <= sell_th:
            state = -1

        if state == 1:
            labels.append("GÜÇLÜ AL" if s >= strong_th else "AL")
        elif state == -1:
            labels.append("GÜÇLÜ SAT" if s <= -strong_th else "SAT")
        else:
            labels.append("BEKLE")
    return labels


def latest_recommendation(df_with_signals: pd.DataFrame) -> dict:
    """En son bar için özet öneri sözlüğü döndürür."""
    last = df_with_signals.iloc[-1]
    return {
        "datetime": str(df_with_signals.index[-1]),
        "close": round(float(last["close"]), 4),
        "signal": last["signal"],
        "score": round(float(last["score"]), 3),
        "confidence_pct": float(last["confidence"]),
        "rsi": round(float(last["rsi"]), 2) if not pd.isna(last["rsi"]) else None,
        "adx": round(float(last["adx"]), 2) if not pd.isna(last["adx"]) else None,
        "note": (
            "Bu bir yatırım tavsiyesi değildir. Sinyal, seçilen indikatörlerin "
            "ağırlıklı ortak görüşünü yansıtır; kesinlik iddia etmez."
        ),
    }
