"""
data_fetcher.py
----------------
yfinance üzerinden geçmiş fiyat verisi çeker. Hisse (BIST için ".IS" suffix,
örn. THYAO.IS), ABD hisseleri (AAPL), endeks veya kripto (BTC-USD) sembolleri
desteklenir.

Not: yfinance intraday verilerde (1m/5m/15m/30m/60m) geriye dönük süreyi
sınırlar (Yahoo Finance API kısıtı). Bu modül izin verilen maksimum periyodu
otomatik ayarlar ve kullanıcıyı bilgilendirir.
"""

from __future__ import annotations
import sys
import pandas as pd

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None

# Yahoo Finance'in intraday interval'ler için izin verdiği yaklaşık maksimum
# geçmiş veri aralığı (kısıtları aşmamak için otomatik sınırlama yapılır).
MAX_PERIOD_FOR_INTERVAL = {
    "1m": "7d",
    "5m": "60d",
    "15m": "60d",
    "30m": "60d",
    "60m": "730d",
    "1h": "730d",
    "1d": "10y",
    "1wk": "20y",
}

SUPPORTED_INTERVALS = list(MAX_PERIOD_FOR_INTERVAL.keys())

# Zaman aralığına göre varsayılan trailing-stop ATR çarpanı. Kısa aralıklarda
# (1m/5m/15m) ATR fiyata oranla daha "gürültülü" davrandığı için daha geniş
# (toleranslı) bir çarpan; günlük/haftalıkta ise daha dar bir çarpan yeterli
# oluyor. THYAO.IS üzerinde yapılan gerçek testlerle kabaca doğrulanmıştır
# (bkz. README - "Zaman Aralığı Karşılaştırması" notu). Gerekirse
# main.py/compare_intervals.py/app.py üzerinden elle ezilebilir.
DEFAULT_TRAILING_ATR_MULT = {
    "1m": 6.0,
    "5m": 6.0,
    "15m": 5.5,
    "30m": 5.0,
    "60m": 5.0,
    "1h": 5.0,
    "1d": 3.0,
    "1wk": 3.0,
}


def default_trailing_atr_mult(interval: str) -> float:
    return DEFAULT_TRAILING_ATR_MULT.get(normalize_interval(interval), 4.0)


def normalize_interval(interval: str) -> str:
    interval = interval.strip().lower()
    aliases = {
        "5dk": "5m", "15dk": "15m", "1s": "1h", "1sa": "1h",
        "1saat": "1h", "1gun": "1d", "1gün": "1d", "gunluk": "1d",
        "günlük": "1d", "haftalik": "1wk", "haftalık": "1wk",
    }
    interval = aliases.get(interval, interval)
    if interval not in SUPPORTED_INTERVALS:
        raise ValueError(
            f"Desteklenmeyen zaman aralığı: '{interval}'. "
            f"Desteklenenler: {SUPPORTED_INTERVALS}"
        )
    return interval


def fetch_ohlcv(ticker: str, interval: str = "1h", period: str | None = None) -> pd.DataFrame:
    """
    ticker : ör. 'THYAO.IS', 'AAPL', 'BTC-USD'
    interval : '1m','5m','15m','30m','60m'/'1h','1d','1wk'
    period : yfinance period string ('60d','1y', vs.). None ise interval'a
             göre otomatik en uygun (izinli maksimuma yakın) değer seçilir.
    """
    if yf is None:
        raise RuntimeError(
            "yfinance kurulu değil. Kurmak için: pip install yfinance"
        )

    interval = normalize_interval(interval)
    if period is None:
        period = MAX_PERIOD_FOR_INTERVAL[interval]

    df = yf.download(
        tickers=ticker,
        interval=interval,
        period=period,
        auto_adjust=True,
        progress=False,
        multi_level_index=False,
    )

    if df is None or df.empty:
        raise ValueError(
            f"'{ticker}' için veri bulunamadı. Sembolü ve interval/period "
            f"kombinasyonunu kontrol edin (örn. Yahoo Finance sembol formatı)."
        )

    df = df.rename(columns={
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
    })
    df = df[["open", "high", "low", "close", "volume"]].dropna()
    df.index.name = "datetime"
    return df


def synthetic_ohlcv(n: int = 500, start_price: float = 100.0, seed: int = 42) -> pd.DataFrame:
    """
    Test / demo amaçlı, internete ihtiyaç duymayan sentetik OHLCV verisi
    üretir (geometrik random walk). yfinance verisine erişim olmadığında
    motoru denemek için kullanılabilir.
    """
    import numpy as np
    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=0.0002, scale=0.01, size=n)
    close = start_price * np.exp(np.cumsum(returns))

    high = close * (1 + np.abs(rng.normal(0, 0.003, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.003, n)))
    open_ = close * (1 + rng.normal(0, 0.002, n))
    volume = rng.integers(100_000, 1_000_000, n)

    idx = pd.date_range(end=pd.Timestamp.today(), periods=n, freq="h")
    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )
    df.index.name = "datetime"
    return df


if __name__ == "__main__":
    t = sys.argv[1] if len(sys.argv) > 1 else "THYAO.IS"
    iv = sys.argv[2] if len(sys.argv) > 2 else "1d"
    data = fetch_ohlcv(t, iv)
    print(data.tail())
