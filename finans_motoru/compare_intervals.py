"""
compare_intervals.py
---------------------
Aynı hisse/sembol için birden fazla zaman aralığını (5dk, 15dk, 1sa, 1gün ...)
otomatik olarak çekip backtest eder ve sonuçları tek bir karşılaştırma
tablosunda gösterir. Böylece "bu hisse için hangi zaman dilimi daha iyi
çalışıyor?" sorusuna hızlıca cevap bulabilirsiniz.

Kullanım:
    python compare_intervals.py --ticker THYAO.IS
    python compare_intervals.py --ticker AAPL --intervals 15m,1h,1d
    python compare_intervals.py --demo                       # internetsiz test
"""

from __future__ import annotations
import argparse
import sys

import pandas as pd

from data_fetcher import fetch_ohlcv, synthetic_ohlcv, normalize_interval, default_trailing_atr_mult
from signal_engine import compute_signals, latest_recommendation
from backtest import run_backtest

DEFAULT_INTERVALS = ["15m", "1h", "1d"]


def parse_args():
    p = argparse.ArgumentParser(description="Farklı zaman aralıklarını karşılaştır")
    p.add_argument("--ticker", type=str, default="THYAO.IS")
    p.add_argument("--intervals", type=str, default=",".join(DEFAULT_INTERVALS),
                    help="Virgülle ayrılmış liste, ör: 5m,15m,1h,1d")
    p.add_argument("--capital", type=float, default=10_000.0)
    p.add_argument("--commission-bps", type=float, default=5.0)
    p.add_argument("--stop-loss", type=float, default=0.03)
    p.add_argument("--position-size", type=float, default=0.20,
                    help="Her işlemde sermayenin ne kadarının kullanılacağı (0.20 = %%20)")
    p.add_argument("--take-profit", type=float, default=None)
    p.add_argument("--trailing-atr-mult", type=float, default=None,
                    help="Boş bırakılırsa her zaman aralığı kendi otomatik çarpanını kullanır")
    p.add_argument("--demo", action="store_true", help="İnternetsiz sentetik veriyle test")
    p.add_argument("--out", type=str, default="karsilastirma.csv")
    return p.parse_args()


def main():
    args = parse_args()
    intervals = [normalize_interval(i) for i in args.intervals.split(",") if i.strip()]

    rows = []
    for interval in intervals:
        print(f"-> {interval} çekiliyor ve test ediliyor...")
        try:
            if args.demo:
                # Her interval için farklı bir seed kullanarak biraz çeşitlilik sağla
                df = synthetic_ohlcv(n=600, seed=hash(interval) % 1000)
            else:
                df = fetch_ohlcv(args.ticker, interval)

            signals_df = compute_signals(df)

            if args.trailing_atr_mult is None:
                trailing_mult = default_trailing_atr_mult(interval)
            elif args.trailing_atr_mult <= 0:
                trailing_mult = None
            else:
                trailing_mult = args.trailing_atr_mult

            result = run_backtest(
                signals_df,
                initial_capital=args.capital,
                commission_bps=args.commission_bps,
                stop_loss_pct=args.stop_loss,
                take_profit_pct=args.take_profit,
                trailing_atr_mult=trailing_mult,
                position_size_pct=args.position_size,
            )
            rec = latest_recommendation(signals_df)
            m = result.metrics
            rows.append({
                "interval": interval,
                "trailing_mult": trailing_mult,
                "bar_sayisi": len(df),
                "guncel_sinyal": rec["signal"],
                "guncel_skor": rec["score"],
                "getiri_%": m.get("total_return_pct"),
                "al_tut_getiri_%": m.get("buy_hold_return_pct"),
                "islem_sayisi": m.get("num_trades"),
                "kazanma_orani_%": m.get("win_rate_pct"),
                "profit_factor": m.get("profit_factor"),
                "max_dusus_%": m.get("max_drawdown_pct"),
                "sharpe": m.get("sharpe_ratio_annualized"),
            })
        except Exception as e:
            print(f"   HATA ({interval}): {e}")
            rows.append({"interval": interval, "hata": str(e)})

    if not rows:
        print("Hiçbir sonuç üretilemedi.")
        sys.exit(1)

    table = pd.DataFrame(rows)
    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", 20)
    print("\n================ ZAMAN ARALIĞI KARŞILAŞTIRMASI ================")
    print(table.to_string(index=False))

    table.to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"\nTablo kaydedildi: {args.out}")

    if "getiri_%" in table.columns and table["getiri_%"].notna().any():
        best = table.loc[table["getiri_%"].idxmax()]
        print(f"\nEn yüksek backtest getirisi: {best['interval']} "
              f"({best['getiri_%']}%, {best['islem_sayisi']} işlem, "
              f"profit_factor={best['profit_factor']})")
        print("Not: Bu geçmiş performanstır, gelecekte aynı sonucu vermez. "
              "İşlem sayısı az olan zaman aralıklarında sonuç istatistiksel "
              "olarak daha az güvenilirdir.")


if __name__ == "__main__":
    main()
