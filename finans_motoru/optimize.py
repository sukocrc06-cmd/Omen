"""
optimize.py
------------
Belirli bir zaman aralığı (varsayılan: 1 saatlik) için motorun parametrelerini
"walk-forward" mantığıyla arar: tek bir dönemde iyi görünen ama başka dönemde
çöken ("overfit" / ezber) parametre setlerini elemeyi hedefler.

YÖNTEM:
1) Veri kronolojik olarak 3 eşit parçaya (bölüm) ayrılır.
2) Rastgele parametre adayları üretilir (indikatör periyotları, AL/SAT eşikleri,
   trailing-stop çarpanı, stop-loss, pozisyon büyüklüğü).
3) Her aday, 3 bölümün HER BİRİNDE ayrı ayrı test edilir (bölümler birbirinden
   bağımsız zaman dilimleridir -> "farklı dönemlerde de işe yarıyor mu?").
4) Sıralama TEK bir dönemin getirisine göre değil, üç dönem ortalaması EKSİ
   üç dönem arasındaki tutarsızlık (std sapma) ile yapılır. Yani "her zaman
   orta karar iyi" bir aday, "bir dönemde harika, diğerinde felaket" bir
   adaya tercih edilir.
5) İşlem sayısı çok az olan (istatistiksel olarak güvenilmez) adaylar elenir.

NOT: Bu optimizasyon geçmiş veri üzerinde çalışır. Bulunan "en iyi" parametreler
geleceği garanti etmez; sadece geçmişte daha TUTARLI çalışmış olanı bulmaya
çalışır. Sonuçlar mutlaka farklı bir test döneminde (out-of-sample) veya farklı
bir hissede de kontrol edilmelidir.

Kullanım:
    python optimize.py --ticker THYAO.IS --interval 1h --trials 60
    python optimize.py --csv rapor_sinyaller_ham.csv --trials 40
    (--csv, indikatörsüz ham OHLCV CSV bekler: open,high,low,close,volume kolonları)
"""

from __future__ import annotations
import argparse
import json
import random
import sys

import numpy as np
import pandas as pd

from data_fetcher import fetch_ohlcv, normalize_interval
from signal_engine import compute_signals
from backtest import run_backtest

PARAM_SPACE = {
    "ema_fast": [5, 8, 9, 12],
    "ema_slow": [18, 21, 26, 34],
    "ema_trend": [40, 50, 60, 100],
    "rsi_len": [10, 14, 21],
    "buy_th": [0.20, 0.25, 0.30, 0.35],
    "strong_th": [0.50, 0.55, 0.60, 0.65],
    "trailing_atr_mult": [3.0, 4.0, 5.0, 6.0],
    "stop_loss_pct": [0.02, 0.03, 0.04],
    "position_size_pct": [0.15, 0.20, 0.25],
}

# TREND modu: çıkışları kasıtlı olarak gevşetir - amaç "büyük hareketi elden
# kaçırma" pahasına daha uzun süre pozisyonda kalmak. Bunun bedeli daha büyük
# ara düşüşlerdir (drawdown) - bu bir bug değil, bilinçli bir risk/getiri
# tercihidir ve öyle sunulmalıdır.
TREND_PARAM_SPACE = {
    "trailing_atr_mult": [6.0, 8.0, 10.0, 12.0],   # daha geniş -> daha geç çıkar
    "stop_loss_pct": [0.05, 0.07, 0.09],            # daha geniş stop -> ufak sarsıntılarda atılmaz
    "sell_th": [-0.35, -0.45, -0.55, -0.65],        # çıkmak için daha GÜÇLÜ ters sinyal gerekir
    "position_size_pct": [0.20, 0.30, 0.40],        # trend modunda biraz daha büyük pay (daha riskli)
}


def sample_params(rng: random.Random, mode: str = "robust") -> dict:
    ema_fast = rng.choice(PARAM_SPACE["ema_fast"])
    ema_slow = rng.choice([v for v in PARAM_SPACE["ema_slow"] if v > ema_fast])
    ema_trend = rng.choice([v for v in PARAM_SPACE["ema_trend"] if v > ema_slow])
    buy_th = rng.choice(PARAM_SPACE["buy_th"])
    strong_th = rng.choice([v for v in PARAM_SPACE["strong_th"] if v > buy_th])

    if mode == "trend":
        return {
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
            "ema_trend": ema_trend,
            "rsi_len": rng.choice(PARAM_SPACE["rsi_len"]),
            "buy_th": buy_th,
            "sell_th": rng.choice(TREND_PARAM_SPACE["sell_th"]),  # asimetrik: girişten bağımsız, sert eşik
            "strong_th": strong_th,
            "trailing_atr_mult": rng.choice(TREND_PARAM_SPACE["trailing_atr_mult"]),
            "stop_loss_pct": rng.choice(TREND_PARAM_SPACE["stop_loss_pct"]),
            "position_size_pct": rng.choice(TREND_PARAM_SPACE["position_size_pct"]),
        }

    return {
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
        "ema_trend": ema_trend,
        "rsi_len": rng.choice(PARAM_SPACE["rsi_len"]),
        "buy_th": buy_th,
        "sell_th": -buy_th,
        "strong_th": strong_th,
        "trailing_atr_mult": rng.choice(PARAM_SPACE["trailing_atr_mult"]),
        "stop_loss_pct": rng.choice(PARAM_SPACE["stop_loss_pct"]),
        "position_size_pct": rng.choice(PARAM_SPACE["position_size_pct"]),
    }


def _split_chunks(df: pd.DataFrame, n_chunks: int = 3):
    n = len(df)
    size = n // n_chunks
    chunks = []
    for i in range(n_chunks):
        start = i * size
        end = (i + 1) * size if i < n_chunks - 1 else n
        chunks.append(df.iloc[start:end])
    return chunks


def evaluate(df: pd.DataFrame, params: dict, min_trades_per_chunk: int = 4) -> dict | None:
    cfg = {
        "ema_fast": params["ema_fast"],
        "ema_slow": params["ema_slow"],
        "ema_trend": params["ema_trend"],
        "rsi_len": params["rsi_len"],
    }
    try:
        signals_df = compute_signals(
            df, cfg=cfg, buy_th=params["buy_th"], sell_th=params["sell_th"], strong_th=params["strong_th"]
        )
    except Exception:
        return None

    chunks = _split_chunks(signals_df, 3)
    sharpes, returns, trades_counts, drawdowns, buyholds = [], [], [], [], []
    for chunk in chunks:
        if len(chunk) < 50:
            return None
        result = run_backtest(
            chunk,
            initial_capital=10_000.0,
            stop_loss_pct=params["stop_loss_pct"],
            take_profit_pct=None,
            trailing_atr_mult=params["trailing_atr_mult"],
            position_size_pct=params["position_size_pct"],
        )
        m = result.metrics
        if not m or m.get("num_trades", 0) < min_trades_per_chunk:
            return None
        sharpes.append(m["sharpe_ratio_annualized"])
        returns.append(m["total_return_pct"])
        trades_counts.append(m["num_trades"])
        drawdowns.append(m["max_drawdown_pct"])
        buyholds.append(m["buy_hold_return_pct"])

    sharpes = np.array(sharpes)
    robustness = float(sharpes.mean() - sharpes.std())
    avg_return = float(np.mean(returns))
    avg_buyhold = float(np.mean(buyholds))
    # trend'i ne kadar "yakaladık" - sadece pozitif al-tut dönemlerinde anlamlı
    capture_ratio = round(avg_return / avg_buyhold, 3) if avg_buyhold > 0.5 else None
    return {
        "params": params,
        "avg_sharpe": round(float(sharpes.mean()), 3),
        "sharpe_std": round(float(sharpes.std()), 3),
        "robustness_score": round(robustness, 3),
        "avg_return_pct": round(avg_return, 2),
        "avg_buyhold_pct": round(avg_buyhold, 2),
        "capture_ratio": capture_ratio,
        "worst_drawdown_pct": round(float(np.min(drawdowns)), 2),
        "min_trades_in_a_chunk": int(min(trades_counts)),
        "chunk_sharpes": [round(float(x), 3) for x in sharpes],
        "chunk_returns_pct": [round(float(x), 2) for x in returns],
    }


def parse_args():
    p = argparse.ArgumentParser(description="1 saatlik (veya seçilen aralık) için walk-forward parametre araması")
    p.add_argument("--ticker", type=str, default="THYAO.IS")
    p.add_argument("--interval", type=str, default="1h")
    p.add_argument("--period", type=str, default=None)
    p.add_argument("--csv", type=str, default=None, help="Ham OHLCV CSV (indeks=zaman, kolonlar: open,high,low,close,volume)")
    p.add_argument("--trials", type=int, default=60, help="Denenecek rastgele parametre kombinasyonu sayısı")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", type=str, default="en_iyi_parametreler.json")
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--mode", type=str, default="robust", choices=["robust", "trend"],
                    help="robust: düşük riskli/tutarlı ayar arar (varsayılan). "
                         "trend: büyük trendleri daha çok yakalamak için çıkışları gevşetir "
                         "- karşılığında daha büyük düşüşlere (drawdown) açık olur.")
    p.add_argument("--max-drawdown", type=float, default=40.0,
                    help="(sadece --mode trend) Bu yüzdeden daha kötü düşüşü olan adaylar elenir")
    return p.parse_args()


def main():
    args = parse_args()
    interval = normalize_interval(args.interval)

    if args.csv:
        df = pd.read_csv(args.csv, index_col=0, parse_dates=True)
        print(f"CSV yüklendi: {len(df)} satır ({args.csv})")
    else:
        print(f"Veri çekiliyor: {args.ticker} / {interval} ...")
        try:
            df = fetch_ohlcv(args.ticker, interval, args.period)
        except Exception as e:
            print(f"HATA: Veri çekilemedi ({e})")
            sys.exit(1)
        print(f"{len(df)} bar alındı ({df.index[0]} .. {df.index[-1]})")

    rng = random.Random(args.seed)
    seen = set()
    results = []
    tried = 0
    while tried < args.trials:
        params = sample_params(rng, mode=args.mode)
        key = tuple(sorted(params.items()))
        if key in seen:
            continue
        seen.add(key)
        tried += 1
        r = evaluate(df, params)
        if r is not None:
            if args.mode == "trend" and r["worst_drawdown_pct"] < -args.max_drawdown:
                pass  # çok büyük düşüş -> ele
            else:
                results.append(r)
        if tried % 10 == 0:
            print(f"  ... {tried}/{args.trials} deneme tamamlandı ({len(results)} geçerli aday)")

    if not results:
        print("\nHiçbir aday minimum işlem sayısı / max-drawdown şartını geçemedi. "
              "--trials sayısını artırın ya da --max-drawdown gevşetin.")
        sys.exit(1)

    if args.mode == "trend":
        results.sort(key=lambda r: r["avg_return_pct"], reverse=True)
        top = results[: args.top]
        print("\n================ EN ÇOK GETİRİ/TREND YAKALAYAN ADAYLAR (TREND MODU) ================")
        print(f"(--max-drawdown %{args.max_drawdown}'den kötü olanlar zaten elendi)")
        for i, r in enumerate(top, 1):
            capture = f"%{round(r['capture_ratio']*100,1)}" if r['capture_ratio'] is not None else "n/a"
            print(f"\n#{i}  avg_getiri=%{r['avg_return_pct']}  avg_al_tut=%{r['avg_buyhold_pct']}  "
                  f"yakalama_orani={capture}  en_kotu_dusus=%{r['worst_drawdown_pct']}  "
                  f"avg_sharpe={r['avg_sharpe']} (sapma={r['sharpe_std']})")
            print(f"    Bölüm bazında Getiri%: {r['chunk_returns_pct']}")
            print(f"    Parametreler: {json.dumps(r['params'], ensure_ascii=False)}")
        print("\nÖNEMLİ: 'yakalama_orani', o hissenin kendi yükselişinin (al-tut getirisi) ne "
              "kadarını motorun yakaladığını gösterir (yalnızca al-tut pozitifse anlamlıdır). "
              "%100'e ne kadar yakınsa o kadar iyi 'trend yakalama', ama bu adaylar robust modun "
              "adaylarından DAHA BÜYÜK düşüşlere (drawdown) sahiptir - bilerek. Küçük bir hesapla "
              "(2000 TL gibi) bu daha büyük duygusal ve parasal risk demektir.")
    else:
        results.sort(key=lambda r: r["robustness_score"], reverse=True)
        top = results[: args.top]
        print("\n================ EN TUTARLI (ROBUST) PARAMETRE ADAYLARI ================")
        for i, r in enumerate(top, 1):
            print(f"\n#{i}  robustness={r['robustness_score']}  avg_sharpe={r['avg_sharpe']} "
                  f"(sapma={r['sharpe_std']})  avg_getiri=%{r['avg_return_pct']}  "
                  f"en_kotu_dusus=%{r['worst_drawdown_pct']}")
            print(f"    Bölüm bazında Sharpe: {r['chunk_sharpes']}  |  Getiri%: {r['chunk_returns_pct']}")
            print(f"    Parametreler: {json.dumps(r['params'], ensure_ascii=False)}")

    best = top[0]
    out_path = args.out
    if args.mode == "trend" and args.out == "en_iyi_parametreler.json":
        out_path = "en_iyi_parametreler_trend.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(best["params"], f, ensure_ascii=False, indent=2)
    print(f"\nEn iyi parametre seti kaydedildi: {out_path}")
    print("\nNOT: 'En iyi' burada TEK bir dönemde en yüksek getiriyi değil, birden fazla "
          "zaman diliminde ölçülen bir hedefi (mod'a göre tutarlılık ya da getiri) ifade eder. "
          "Yine de bu geçmiş veridir; gelecekte aynı şekilde çalışacağının garantisi yoktur. "
          "Bu parametreleri main.py / screen_tickers.py / rolling_windows.py ile --params-file "
          "üzerinden kullanabilirsiniz.")


if __name__ == "__main__":
    main()
