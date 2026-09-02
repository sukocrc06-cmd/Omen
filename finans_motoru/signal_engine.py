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

from indicators import add_all_indicators, higher_tf_trend


DEFAULT_WEIGHTS = {
    "ema_cross": 1.2,      # kısa/uzun EMA kesişimi (trend yönü)
    "trend_filter": 0.8,   # fiyat vs EMA50 (ana trend filtresi)
    "macd": 1.0,           # MACD histogram yönü
    "rsi": 1.0,            # RSI aşırı alım/satım + orta çizgi
    "bollinger": 0.7,      # fiyatın bantlara göre konumu
    "stochastic": 0.7,     # stokastik kesişim + bölge
    "volume": 0.6,         # hacim teyidi
}

# ADX rejim filtresi: hangi bileşenlerin "trend takibi" (ADX yükseldikçe
# güçlenmeli) ve hangilerinin "ortalamaya dönüş" (ADX düştükçe, yani piyasa
# yatayken güçlenmeli) mantığında olduğunu belirtir. Listede olmayan
# bileşenler (rsi, macd'nin momentum kısmı, stochastic, volume) rejimden
# bağımsız sabit ağırlıkla kalır.
TREND_FOLLOWING_COMPONENTS = {"ema_cross", "trend_filter"}
MEAN_REVERSION_COMPONENTS = {"bollinger"}

ADX_LOW = 18.0   # bu ve altı: piyasa yatay/trendsiz kabul edilir
ADX_HIGH = 28.0  # bu ve üstü: piyasa net trendli kabul edilir

# Karşı-trend (üst zaman dilimiyle çelişen) sinyallerin ne kadar bastırılacağı.
# 1.0 = hiç bastırma, 0.0 = tamamen sustur. Düşük bir değer (tam kapatmak
# yerine) seçildi ki çok güçlü confluence'lı karşı-trend sinyaller yine de
# (zayıflamış olarak) görülebilsin.
HTF_COUNTERTREND_DAMPEN = 0.4


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
    # Bölge sınırlarında (30/45/55/70) ani sıçrama yerine, her bölgenin
    # merkezi arasında lineer enterpolasyon yapılır -> aynı "aşırı satımda
    # dönüş beklentisi (+), hafif ayı (-), nötr (0), hafif boğa (+), aşırı
    # alımda dönüş beklentisi (-)" mantığı korunur ama eşiğe yakın barlarda
    # skor artık aniden zıplamak yerine yumuşak geçer (histerezisin gereksiz
    # tetiklenmesini azaltır).
    anchors_r = [15, 37.5, 50, 62.5, 85]
    anchors_s = [1.0, -0.4, 0.0, 0.4, -1.0]
    score = pd.Series(np.interp(r, anchors_r, anchors_s), index=df.index)
    score[r.isna()] = np.nan
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
    price_vol_score = (direction * confirm).fillna(0.0)

    # OBV'nin kısa vadeli eğimi (son 5 bar): tek bir bardaki hacim
    # sıçramasından çok daha az gürültülü bir "para akışı" teyidi sağlar.
    obv_slope = df["obv"].diff(5)
    obv_score = np.sign(obv_slope).fillna(0.0)

    return (0.6 * price_vol_score + 0.4 * obv_score).clip(-1, 1)


def _adx_regime_multiplier(adx: pd.Series, component: str) -> pd.Series:
    """
    ADX'e göre bileşen ağırlığını 0.5x-1.0x (ya da 1.0x-0.5x) arasında
    dinamik ölçekler. ADX hiç kullanılmıyordu (sadece raporlanıyordu); burada
    "rejim filtresi" olarak devreye sokuluyor:
    - Trend-takip bileşenleri (ema_cross, trend_filter): ADX düşükken
      (yatay piyasa) whipsaw riski yüksek olduğu için ağırlıkları yarıya
      iner; ADX yükseldikçe (net trend) tam ağırlığa döner.
    - Ortalamaya-dönüş bileşeni (bollinger): tam tersi - net trendde fiyat
      banda yaslanıp kalabildiği için (yanlış SAT/AL üretir) ağırlığı düşer;
      yatay piyasada tam ağırlıkta kalır.
    Diğer bileşenler (rsi, macd, stochastic, volume) rejimden etkilenmez.
    """
    if component not in TREND_FOLLOWING_COMPONENTS and component not in MEAN_REVERSION_COMPONENTS:
        return pd.Series(1.0, index=adx.index)

    adx_filled = adx.fillna(ADX_LOW)  # veri başındaki NaN'larda nötr (düşük) davran
    trend_strength = ((adx_filled - ADX_LOW) / (ADX_HIGH - ADX_LOW)).clip(0, 1)

    if component in TREND_FOLLOWING_COMPONENTS:
        return 0.5 + 0.5 * trend_strength
    return 1.0 - 0.5 * trend_strength


def _infer_htf_rule(index: pd.DatetimeIndex) -> str | None:
    """Bar aralığından otomatik olarak makul bir üst zaman dilimi seçer."""
    if len(index) < 3:
        return None
    delta_minutes = (index[1] - index[0]).total_seconds() / 60
    if delta_minutes <= 0:
        return None
    if delta_minutes <= 30:       # 1m/5m/15m/30m -> 4 saatlik trend
        return "4h"
    if delta_minutes <= 240:      # 1h/2h/4h -> günlük trend
        return "1D"
    if delta_minutes <= 1440:     # günlük -> haftalık trend
        return "1W"
    return None  # zaten haftalık/daha büyükse üst zaman dilimi teyidi anlamsız


def compute_signals(df: pd.DataFrame, cfg: dict | None = None, weights: dict | None = None,
                     buy_th: float = 0.30, sell_th: float = -0.30, strong_th: float = 0.60,
                     htf_confirm: bool = False) -> pd.DataFrame:
    """
    df: OHLCV DataFrame (open, high, low, close, volume).
    buy_th/sell_th/strong_th: sinyal eşikleri (bkz. _hysteresis_labels). optimize.py
        tarafından zaman aralığına özel ayarlanabilir hale getirmek için parametrelendirildi.
    htf_confirm: True ise, bar aralığından otomatik seçilen bir üst zaman
        diliminin (ör. 1 saatlik barlar için günlük) trendiyle çelişen
        sinyaller bastırılır (bkz. HTF_COUNTERTREND_DAMPEN). cfg içinde
        "htf_rule" (ör. "1D", "4h") verilerek elle ezilebilir, "htf_ema_len"
        ile üst-TF trend EMA uzunluğu değiştirilebilir.
        VARSAYILAN KAPALI: THYAO.IS/1h üzerinde gerçek veriyle test edildiğinde
        (bkz. README) günlük EMA(50) trendi çok yavaş/gecikmeli kaldığı için
        tam olarak en kârlı işlemleri (erken trend dönüşlerini) bastırıp
        Sharpe'ı düşürdü - birden fazla dampen/EMA-uzunluğu kombinasyonuyla
        doğrulandı. Yine de farklı hisse/aralıkta işe yarayabilir; denemek
        isteyenler için parametre olarak açık bırakıldı.
    Dönüş: indikatörler + 'score' (-1..1), 'signal' (AL/SAT/BEKLE), 'confidence' (0-100).
    """
    cfg = cfg or {}
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

    # ADX rejim filtresi: her bileşenin ağırlığını bar bazında ölçekler
    # (bkz. _adx_regime_multiplier). Böylece toplam ağırlık da bar bazında
    # değişir; normalize etmek için payda da Series olarak hesaplanır.
    weight_series = {
        k: weights[k] * _adx_regime_multiplier(out["adx"], k) for k in components
    }
    total_weight = sum(weight_series.values())
    weighted_sum = sum(components[k].fillna(0) * weight_series[k] for k in components)
    score = (weighted_sum / total_weight).clip(-1, 1)

    # Ham skoru kısa bir hareketli ortalamayla yumuşat (tek bar'lık gürültüyü azaltır)
    smooth_score = score.rolling(window=3, min_periods=1).mean()

    # Üst zaman dilimi trend teyidi: ana trendin tersine düşen sinyalleri bastır.
    htf_rule = cfg.get("htf_rule", "auto") if htf_confirm else None
    if htf_rule == "auto":
        htf_rule = _infer_htf_rule(out.index)
    if htf_rule:
        htf_trend = higher_tf_trend(out, htf_rule, cfg.get("htf_ema_len", 50))
        out["htf_trend"] = htf_trend
        score_sign = np.sign(smooth_score)
        countertrend = htf_trend.notna() & (score_sign != 0) & (score_sign != htf_trend)
        smooth_score = smooth_score.mask(countertrend, smooth_score * HTF_COUNTERTREND_DAMPEN)
    else:
        out["htf_trend"] = np.nan

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
