"""
main.py
-------
Komut satırı arayüzü: veri çek -> indikatör+sinyal hesapla -> backtest et ->
rapor yaz + grafik üret.

Kullanım örnekleri:
    python main.py --ticker THYAO.IS --interval 1h --period 60d
    python main.py --ticker AAPL --interval 15m --period 30d --capital 5000
    python main.py --demo --interval 1d          # internete gerek duymadan test

Zaman aralığı seçenekleri: 1m, 5m, 15m, 30m, 60m/1h, 1d, 1wk
(5 dakikalık, 15 dakikalık, 1 saatlik, günlük -> hepsi desteklenir)
"""

from __future__ import annotations
import argparse
import json
import sys

import pandas as pd

from data_fetcher import fetch_ohlcv, synthetic_ohlcv, normalize_interval, default_trailing_atr_mult
from signal_engine import compute_signals, latest_recommendation
from backtest import run_backtest


def parse_args():
    p = argparse.ArgumentParser(description="Finans Alım-Satım Sinyal & Backtest Motoru")
    p.add_argument("--ticker", type=str, default="THYAO.IS", help="Örn: THYAO.IS, AAPL, BTC-USD")
    p.add_argument("--interval", type=str, default="1h",
                    help="1m,5m,15m,30m,60m/1h,1d,1wk")
    p.add_argument("--period", type=str, default=None,
                    help="ör. 60d, 1y (boş bırakılırsa interval'a göre otomatik seçilir)")
    p.add_argument("--capital", type=float, default=10_000.0, help="Başlangıç sermayesi")
    p.add_argument("--commission-bps", type=float, default=5.0, help="İşlem başına komisyon (baz puan)")
    p.add_argument("--allow-short", action="store_true", help="Short pozisyonlara izin ver")
    p.add_argument("--stop-loss", type=float, default=0.03, help="Stop-loss yüzdesi (0.03 = %%3)")
    p.add_argument("--position-size", type=float, default=0.20,
                    help="Her işlemde sermayenin ne kadarının kullanılacağı (0.20 = %%20). "
                         "1.0 = tüm sermaye (yüksek risk, önerilmez)")
    p.add_argument("--take-profit", type=float, default=None,
                    help="Sabit take-profit yüzdesi (varsayılan: kapalı, trailing-stop kullanılır)")
    p.add_argument("--trailing-atr-mult", type=float, default=None,
                    help="Trailing stop için ATR çarpanı (boş bırakılırsa zaman aralığına göre "
                         "otomatik seçilir; 0 verilirse trailing stop tamamen kapanır)")
    p.add_argument("--plot", action="store_true", help="Grafik PNG üret")
    p.add_argument("--demo", action="store_true", help="İnternete bağlanmadan sentetik veriyle çalış")
    p.add_argument("--out-prefix", type=str, default="rapor", help="Çıktı dosyaları için ön ek")
    p.add_argument("--params-file", type=str, default=None,
                    help="optimize.py çıktısı JSON dosyası - indikatör periyotlarını, "
                         "sinyal eşiklerini ve risk parametrelerini bu dosyadan uygular "
                         "(verilmezse motorun varsayılanları kullanılır)")
    return p.parse_args()


def _load_params(path: str | None) -> dict:
    if not path:
        return {}
    import json
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    args = parse_args()
    interval = normalize_interval(args.interval)

    print(f"[1/4] Veri çekiliyor: ticker={args.ticker} interval={interval} period={args.period or 'otomatik'}")
    if args.demo:
        df = synthetic_ohlcv(n=800)
        print("   -> DEMO modu: sentetik veri kullanılıyor (gerçek piyasa verisi değildir).")
    else:
        try:
            df = fetch_ohlcv(args.ticker, interval, args.period)
        except Exception as e:
            print(f"HATA: Veri çekilemedi ({e}). --demo bayrağıyla sentetik veri deneyebilirsiniz.")
            sys.exit(1)
    print(f"   -> {len(df)} bar alındı ({df.index[0]} .. {df.index[-1]})")

    params = _load_params(args.params_file)
    if params:
        print(f"   -> Özel parametre dosyası uygulanıyor: {args.params_file}")

    print("[2/4] İndikatörler ve sinyaller hesaplanıyor...")
    cfg = {k: params[k] for k in ("ema_fast", "ema_slow", "ema_trend", "rsi_len") if k in params}
    signals_df = compute_signals(
        df, cfg=cfg or None,
        buy_th=params.get("buy_th", 0.30),
        sell_th=params.get("sell_th", -0.30),
        strong_th=params.get("strong_th", 0.60),
    )

    trailing_mult = args.trailing_atr_mult
    if trailing_mult is None:
        trailing_mult = params.get("trailing_atr_mult") or default_trailing_atr_mult(interval)
        print(f"   -> Trailing-stop ATR çarpanı: {trailing_mult}x "
              f"({'params-file' if 'trailing_atr_mult' in params else interval + ' için otomatik'})")
    elif trailing_mult <= 0:
        trailing_mult = None

    print("[3/4] Backtest çalıştırılıyor...")
    result = run_backtest(
        signals_df,
        initial_capital=args.capital,
        commission_bps=args.commission_bps,
        allow_short=args.allow_short,
        stop_loss_pct=params.get("stop_loss_pct", args.stop_loss),
        take_profit_pct=args.take_profit,
        trailing_atr_mult=trailing_mult,
        position_size_pct=params.get("position_size_pct", args.position_size),
    )

    rec = latest_recommendation(signals_df)

    print("\n================ SON DURUM ÖZETİ ================")
    print(json.dumps(rec, ensure_ascii=False, indent=2))

    print("\n================ BACKTEST METRİKLERİ ================")
    print(json.dumps(result.metrics, ensure_ascii=False, indent=2))

    csv_path = f"{args.out_prefix}_sinyaller.csv"
    signals_df.to_csv(csv_path)
    print(f"\n[4/4] Detaylı sinyal tablosu kaydedildi: {csv_path}")

    if args.plot:
        png_path = f"{args.out_prefix}_grafik.png"
        _plot(signals_df, result, png_path, args.ticker, interval)
        print(f"Grafik kaydedildi: {png_path}")


def _plot(df: pd.DataFrame, result, out_path: str, ticker: str, interval: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True,
                              gridspec_kw={"height_ratios": [3, 1, 1]})

    ax1 = axes[0]
    ax1.plot(df.index, df["close"], label="Kapanış", color="#1f77b4", linewidth=1)
    ax1.plot(df.index, df["ema_fast"], label="EMA hızlı", color="#ff7f0e", linewidth=0.8)
    ax1.plot(df.index, df["ema_slow"], label="EMA yavaş", color="#2ca02c", linewidth=0.8)
    ax1.fill_between(df.index, df["bb_lower"], df["bb_upper"], color="grey", alpha=0.1)

    is_buy = df["signal"].isin(["AL", "GÜÇLÜ AL"])
    is_sell = df["signal"].isin(["SAT", "GÜÇLÜ SAT"])
    # Sadece sinyalin İLK oluştuğu bar'ı işaretle (her bar değil) - grafiği
    # sadeleştirir ve gerçek al/sat "kararı" anlarını gösterir.
    buy_entry = df[is_buy & ~is_buy.shift(1, fill_value=False)]
    sell_entry = df[is_sell & ~is_sell.shift(1, fill_value=False)]
    ax1.scatter(buy_entry.index, buy_entry["close"], marker="^", color="green", s=70, label="AL", zorder=5)
    ax1.scatter(sell_entry.index, sell_entry["close"], marker="v", color="red", s=70, label="SAT", zorder=5)
    ax1.set_title(f"{ticker} ({interval}) - Fiyat & Sinyaller")
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(alpha=0.2)

    ax2 = axes[1]
    ax2.plot(df.index, df["rsi"], color="purple", linewidth=0.8, label="RSI")
    ax2.axhline(70, color="red", linestyle="--", linewidth=0.6)
    ax2.axhline(30, color="green", linestyle="--", linewidth=0.6)
    ax2.set_ylabel("RSI")
    ax2.legend(loc="upper left", fontsize=8)
    ax2.grid(alpha=0.2)

    ax3 = axes[2]
    ax3.plot(result.equity_curve.index, result.equity_curve.values, color="black", linewidth=1)
    ax3.set_ylabel("Equity")
    ax3.grid(alpha=0.2)

    plt.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    main()
