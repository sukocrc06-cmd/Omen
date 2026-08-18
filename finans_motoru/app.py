"""
app.py
------
Motoru başkalarının tarayıcıdan kullanabileceği hale getiren basit bir
Streamlit web arayüzü.

Çalıştırma:
    streamlit run app.py

Yerelde çalışır (http://localhost:8501). İnsanlarla paylaşmak için:
  - Streamlit Community Cloud'a ücretsiz deploy edilebilir (bkz. README).
  - Ya da bir sunucuda `streamlit run app.py --server.port 8501` ile barındırılıp
    bir alan adına yönlendirilebilir.
"""

import streamlit as st
import pandas as pd

from data_fetcher import fetch_ohlcv, synthetic_ohlcv, SUPPORTED_INTERVALS
from signal_engine import compute_signals, latest_recommendation
from backtest import run_backtest

st.set_page_config(page_title="Finans Sinyal & Backtest Motoru", layout="wide")

st.title("📊 Finans Alım-Satım Sinyal & Backtest Motoru")
st.caption(
    "Bu araç yatırım tavsiyesi değildir. Geçmiş veri üzerinde çoklu indikatör "
    "birleşimiyle üretilen olasılıklı sinyalleri gösterir."
)

with st.sidebar:
    st.header("Ayarlar")
    demo = st.checkbox("Demo modu (internetsiz, sentetik veri)", value=False)
    ticker = st.text_input("Sembol (Yahoo Finance formatı)", value="THYAO.IS",
                             help="BIST için '.IS' ekleyin (THYAO.IS), ABD hisseleri için AAPL, kripto için BTC-USD")
    interval = st.selectbox("Zaman aralığı", SUPPORTED_INTERVALS, index=SUPPORTED_INTERVALS.index("1h"))
    period = st.text_input("Periyot (boş = otomatik)", value="")
    capital = st.number_input("Başlangıç sermayesi", value=10_000.0, step=1000.0)
    commission_bps = st.number_input("Komisyon (bps)", value=5.0, step=1.0)
    allow_short = st.checkbox("Short pozisyona izin ver", value=False)
    stop_loss = st.slider("Stop-loss (%)", 0.0, 15.0, 3.0) / 100
    position_size = st.slider("Pozisyon büyüklüğü (sermayenin %'si)", 5, 100, 20,
                                help="Her işlemde sermayenin ne kadarı kullanılsın. Düşük değer "
                                     "= daha az risk, daha düşük max drawdown.") / 100
    use_fixed_tp = st.checkbox("Sabit take-profit kullan (kapalıysa trailing-stop kullanılır)", value=False)
    take_profit = (st.slider("Take-profit (%)", 0.0, 30.0, 6.0) / 100) if use_fixed_tp else None
    trailing_atr_mult = st.slider("Trailing-stop ATR çarpanı", 0.0, 6.0, 3.0,
                                    help="Pozisyon açıldıktan sonraki en iyi fiyattan ATR'nin kaç katı "
                                         "geriye düşülünce çıkılır. 0 = trailing-stop kapalı.")
    run_btn = st.button("Analizi Çalıştır", type="primary")

if run_btn:
    with st.spinner("Veri çekiliyor ve analiz ediliyor..."):
        try:
            if demo:
                df = synthetic_ohlcv(n=800)
                st.info("Demo modu: sentetik veri kullanılıyor.")
            else:
                df = fetch_ohlcv(ticker, interval, period or None)

            signals_df = compute_signals(df)
            result = run_backtest(
                signals_df,
                initial_capital=capital,
                commission_bps=commission_bps,
                allow_short=allow_short,
                stop_loss_pct=stop_loss or None,
                take_profit_pct=take_profit or None,
                trailing_atr_mult=trailing_atr_mult or None,
                position_size_pct=position_size,
            )
            rec = latest_recommendation(signals_df)
        except Exception as e:
            st.error(f"Hata: {e}")
            st.stop()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Güncel Sinyal", rec["signal"])
    col2.metric("Güven (%)", rec["confidence_pct"])
    col3.metric("Skor (-1..1)", rec["score"])
    col4.metric("Son Fiyat", rec["close"])

    st.subheader("Fiyat Grafiği ve Sinyaller")
    chart_df = signals_df[["close", "ema_fast", "ema_slow", "bb_upper", "bb_lower"]]
    st.line_chart(chart_df)

    buys = signals_df[signals_df["signal"].isin(["AL", "GÜÇLÜ AL"])]
    sells = signals_df[signals_df["signal"].isin(["SAT", "GÜÇLÜ SAT"])]
    st.write(f"AL sinyali sayısı: {len(buys)}  |  SAT sinyali sayısı: {len(sells)}")

    st.subheader("Backtest Metrikleri")
    st.json(result.metrics)

    st.subheader("Equity Eğrisi")
    st.line_chart(result.equity_curve)

    st.subheader("Son 30 Bar - Detay Tablo")
    show_cols = ["close", "rsi", "macd_hist", "adx", "score", "confidence", "signal"]
    st.dataframe(signals_df[show_cols].tail(30))

    csv = signals_df.to_csv().encode("utf-8")
    st.download_button("Sinyal Tablosunu CSV İndir", csv, file_name="sinyaller.csv")
else:
    st.info("Soldan ayarları seçip 'Analizi Çalıştır' butonuna basın.")
