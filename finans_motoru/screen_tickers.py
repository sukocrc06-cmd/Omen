"""
screen_tickers.py
-------------------
Birden fazla hisseyi AYNI zaman aralığında (varsayılan: 1 saatlik) tarar ve
motorun (istersen optimize.py ile bulunmuş parametrelerle) her birinde
geçmişte nasıl performans gösterdiğini karşılaştırır.

Amaç: "THYAO mu, ASELSAN mı, yoksa başka bir hisse mi bu stratejiyle daha
tutarlı geçmiş performans gösteriyor?" sorusuna geçmiş veriyle cevap aramak.
Bu bir gelecek tahmini DEĞİLDİR - sadece geçmişte hangi hissede bu kuralların
daha istikrarlı çalıştığını gösterir.

Kullanım:
    python screen_tickers.py --tickers "THYAO.IS,ASELSAN.IS,SISE.IS,KCHOL.IS,BIMAS.IS" --interval 1h
    python screen_tickers.py --tickers "THYAO.IS,ASELSAN.IS" --params-file en_iyi_parametreler.json
    python screen_tickers.py --tickers "THYAO.IS,ASELSAN.IS" --capital 2000 --start-capital-note
"""

from __future__ import annotations
import argparse
import json
import sys

import pandas as pd

from data_fetcher import fetch_ohlcv, normalize_interval, default_trailing_atr_mult
from signal_engine import compute_signals
from backtest import run_backtest

DEFAULT_TICKERS = ["THYAO.IS", "ASELSAN.IS", "SISE.IS", "KCHOL.IS", "BIMAS.IS"]


def load_params(path: str | None) -> dict:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_args():
    p = argparse.ArgumentParser(description="Birden fazla hisseyi aynı zaman aralığında karşılaştır")
    p.add_argument("--tickers", type=str, default=",".join(DEFAULT_TICKERS),
                    help="Virgülle ayrılmış BIST/Yahoo sembolleri")
    p.add_argument("--interval", type=str, default="1h")
    p.add_argument("--capital", type=float, default=2000.0, help="Örnek başlangıç sermayesi (TL)")
    p.add_argument("--commission-bps", type=float, default=5.0)
    p.add_argument("--params-file", type=str, default=None,
                    help="optimize.py çıktısı JSON (ema_fast, ema_slow, ema_trend, rsi_len, buy_th, "
                         "sell_th, strong_th, trailing_atr_mult, stop_loss_pct, position_size_pct)")
    p.add_argument("--out", type=str, default="hisse_taramasi.csv")
    return p.parse_args()


def main():
    args = parse_args()
    interval = normalize_interval(args.interval)
    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    params = load_params(args.params_file)

    cfg = {k: params[k] for k in ("ema_fast", "ema_slow", "ema_trend", "rsi_len") if k in params}
    buy_th = params.get("buy_th", 0.30)
    sell_th = params.get("sell_th", -0.30)
    strong_th = params.get("strong_th", 0.60)
    stop_loss_pct = params.get("stop_loss_pct", 0.03)
    position_size_pct = params.get("position_size_pct", 0.20)
    trailing_atr_mult = params.get("trailing_atr_mult") or default_trailing_atr_mult(interval)

    if params:
        print(f"Özel parametre seti kullanılıyor ({args.params_file})")
    else:
        print("Varsayılan parametreler kullanılıyor (bir optimize.py çıktısı vermediniz)")

    rows = []
    for ticker in tickers:
        print(f"-> {ticker} taranıyor...")
        try:
            df = fetch_ohlcv(ticker, interval)
            signals_df = compute_signals(df, cfg=cfg, buy_th=buy_th, sell_th=sell_th, strong_th=strong_th)
            result = run_backtest(
                signals_df,
                initial_capital=args.capital,
                commission_bps=args.commission_bps,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=None,
                trailing_atr_mult=trailing_atr_mult,
                position_size_pct=position_size_pct,
            )
            m = result.metrics
            rows.append({
                "hisse": ticker,
                "bar_sayisi": len(df),
                "veri_araligi": f"{df.index[0].date()} .. {df.index[-1].date()}",
                "getiri_%": m.get("total_return_pct"),
                "al_tut_getiri_%": m.get("buy_hold_return_pct"),
                "islem_sayisi": m.get("num_trades"),
                "kazanma_orani_%": m.get("win_rate_pct"),
                "profit_factor": m.get("profit_factor"),
                "max_dusus_%": m.get("max_drawdown_pct"),
                "sharpe": m.get("sharpe_ratio_annualized"),
                f"baslangic_{int(args.capital)}_TL_sonuc": m.get("final_equity"),
            })
        except Exception as e:
            print(f"   HATA ({ticker}): {e}")
            rows.append({"hisse": ticker, "hata": str(e)})

    if not rows:
        print("Hiçbir sonuç üretilemedi.")
        sys.exit(1)

    table = pd.DataFrame(rows)
    pd.set_option("display.width", 180)
    pd.set_option("display.max_columns", 20)
    print("\n================ HİSSE TARAMASI (aynı zaman aralığı, aynı kurallar) ================")
    print(table.to_string(index=False))

    table.to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"\nTablo kaydedildi: {args.out}")

    if "sharpe" in table.columns and table["sharpe"].notna().any():
        valid = table.dropna(subset=["sharpe"])
        best = valid.loc[valid["sharpe"].idxmax()]
        print(f"\nGeçmişte en TUTARLI (en yüksek Sharpe) görünen: {best['hisse']} "
              f"(Sharpe={best['sharpe']}, getiri=%{best['getiri_%']}, "
              f"max düşüş=%{best['max_dusus_%']}, {best['islem_sayisi']} işlem)")
        print("\nÖNEMLİ: Bu bir öneri ya da tahmin DEĞİLDİR. Sadece geçmiş veri üzerinde "
              "hangi hissenin bu kurallarla daha istikrarlı sonuç verdiğini gösterir. "
              "İşlem sayısı azsa (ör. <20) istatistiksel güven de düşüktür.")


if __name__ == "__main__":
    main()
