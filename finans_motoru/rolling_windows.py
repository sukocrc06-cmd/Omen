"""
rolling_windows.py
--------------------
"Geçmişte tipik bir ~N aylık dönemde bu motor ne yapardı?" sorusuna TEK bir
sayı yerine bir DAĞILIM (aralık) ile cevap verir. Tüm geçmiş veriyi kaydırmalı
pencerelere böler, her pencerede ayrı ayrı backtest çalıştırır ve sonuçların
min/medyan/maksimumunu, kaç pencerede kayıp olduğunu gösterir.

Bu, "gelecekte kesin şu kadar kazanırsınız" diyen tek bir tahminden çok daha
dürüst bir yöntemdir: geçmişte aynı kurallarla başlanan farklı zaman
noktalarının ne kadar TUTARSIZ ya da TUTARLI sonuç verdiğini gösterir.

Kullanım:
    python rolling_windows.py --ticker ASELS.IS --interval 1h --months 10 --capital 2000
    python rolling_windows.py --ticker KCHOL.IS --interval 1h --months 10 --capital 2000 --params-file en_iyi_parametreler.json
"""

from __future__ import annotations
import argparse
import json
import sys

import pandas as pd

from data_fetcher import fetch_ohlcv, normalize_interval, default_trailing_atr_mult
from signal_engine import compute_signals
from backtest import run_backtest


def parse_args():
    p = argparse.ArgumentParser(description="Kaydırmalı pencere (rolling window) geçmiş performans dağılımı")
    p.add_argument("--ticker", type=str, default="THYAO.IS")
    p.add_argument("--interval", type=str, default="1h")
    p.add_argument("--capital", type=float, default=2000.0)
    p.add_argument("--months", type=float, default=10.0, help="Pencere uzunluğu (ay)")
    p.add_argument("--overlap", type=float, default=0.75, help="Pencereler arası örtüşme oranı (0.75 = %%75 örtüşme)")
    p.add_argument("--params-file", type=str, default=None)
    p.add_argument("--out", type=str, default=None)
    return p.parse_args()


def main():
    args = parse_args()
    interval = normalize_interval(args.interval)
    params = {}
    if args.params_file:
        with open(args.params_file, "r", encoding="utf-8") as f:
            params = json.load(f)

    print(f"Veri çekiliyor: {args.ticker} / {interval} ...")
    try:
        df = fetch_ohlcv(args.ticker, interval)
    except Exception as e:
        print(f"HATA: Veri çekilemedi ({e})")
        sys.exit(1)
    print(f"{len(df)} bar alındı ({df.index[0]} .. {df.index[-1]})")

    cfg = {k: params[k] for k in ("ema_fast", "ema_slow", "ema_trend", "rsi_len") if k in params}
    signals = compute_signals(
        df, cfg=cfg or None,
        buy_th=params.get("buy_th", 0.30), sell_th=params.get("sell_th", -0.30),
        strong_th=params.get("strong_th", 0.60),
    )

    total_bars = len(signals)
    span_days = (signals.index[-1] - signals.index[0]).days
    if span_days <= 0:
        print("Yeterli veri aralığı yok.")
        sys.exit(1)
    bars_per_day = total_bars / span_days
    window_bars = int(bars_per_day * args.months * 30.4)
    if window_bars >= total_bars:
        print(f"HATA: {args.months} aylık pencere ({window_bars} bar), elde olan veriden ({total_bars} bar) uzun. "
              "Daha kısa --months deneyin.")
        sys.exit(1)
    step = max(1, int(window_bars * (1 - args.overlap)))

    trailing_mult = params.get("trailing_atr_mult") or default_trailing_atr_mult(interval)
    stop_loss_pct = params.get("stop_loss_pct", 0.03)
    position_size_pct = params.get("position_size_pct", 0.20)

    rows = []
    start = 0
    while start + window_bars <= total_bars:
        chunk = signals.iloc[start:start + window_bars]
        result = run_backtest(
            chunk, initial_capital=args.capital,
            stop_loss_pct=stop_loss_pct, take_profit_pct=None,
            trailing_atr_mult=trailing_mult, position_size_pct=position_size_pct,
        )
        m = result.metrics
        if m and m.get("num_trades", 0) >= 5:
            rows.append({
                "baslangic": str(chunk.index[0].date()),
                "bitis": str(chunk.index[-1].date()),
                "getiri_%": m["total_return_pct"],
                "sonuc_TL": m["final_equity"],
                "islem_sayisi": m["num_trades"],
                "max_dusus_%": m["max_drawdown_pct"],
            })
        start += step

    if not rows:
        print("Yeterli işlem sayısına sahip pencere bulunamadı (veri çok kısa ya da işlem çok az olabilir).")
        sys.exit(1)

    rdf = pd.DataFrame(rows)
    pd.set_option("display.width", 160)
    print(f"\n================ {args.ticker} - {len(rdf)} adet ~{args.months} aylık kaydırmalı pencere ================")
    print(rdf.to_string(index=False))

    print(f"\n--- ÖZET ---")
    print(f"Getiri%  ->  min: {rdf['getiri_%'].min()}   medyan: {rdf['getiri_%'].median()}   "
          f"ortalama: {round(rdf['getiri_%'].mean(), 2)}   max: {rdf['getiri_%'].max()}")
    print(f"{int(args.capital)} TL sonucu  ->  min: {round(rdf['sonuc_TL'].min())}   "
          f"medyan: {round(rdf['sonuc_TL'].median())}   max: {round(rdf['sonuc_TL'].max())}")
    print(f"Kaç pencerede net KAYIP oldu: {(rdf['getiri_%'] < 0).sum()} / {len(rdf)}")
    print("\nNOT: Bu bir tahmin değildir. Geçmişte farklı başlangıç noktalarının ne kadar "
          "TUTARSIZ ya da TUTARLI sonuç verdiğini gösterir. Pencereler birbiriyle örtüştüğü için "
          "istatistiksel olarak tam bağımsız değildir; yine de kaba bir 'ne kadar değişkenlik "
          "olabilir' fikri verir.")

    out = args.out or f"{args.ticker.replace('.', '_')}_pencere_analizi.csv"
    rdf.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\nTablo kaydedildi: {out}")


if __name__ == "__main__":
    main()
