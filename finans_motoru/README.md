# Finans Alım-Satım Sinyal & Backtest Motoru

Çoklu indikatör (EMA, RSI, MACD, Bollinger Bands, Stokastik, ADX, Hacim)
kullanarak seçilen zaman aralığında (5 dakikalık, 15 dakikalık, 1 saatlik,
1 günlük) geçmiş veri üzerinde backtest yapan ve ağırlıklı puanlamayla
**AL / SAT / BEKLE / GÜÇLÜ AL / GÜÇLÜ SAT** sinyalleri üreten bir sistem.

İki paralel versiyon içerir:

1. **Python motoru** (bu klasördeki `.py` dosyaları) — CLI ve isteğe bağlı
   Streamlit web arayüzü.
2. **Pine Script v5 stratejisi** (`pine/strategy.pine`) — TradingView Pine
   Editör'de doğrudan kullanılabilir, aynı mantığı grafikte gösterir.

> ⚠️ **Not:** Bu araç yatırım tavsiyesi değildir. Sinyaller, seçilen
> indikatörlerin ağırlıklı ortak görüşünü yansıtır; kesinlik iddia etmez.
> Gerçek parayla işlem yapmadan önce mutlaka demo/kağıt hesapta test edin.

---

## 1. Klasör Yapısı

```
finans_motoru/
├── indicators.py      # Tüm teknik indikatörler (EMA, RSI, MACD, BB, Stoch, ADX, ATR, OBV)
├── data_fetcher.py     # yfinance ile veri çekme (hisse/kripto/endeks)
├── signal_engine.py    # İndikatörleri ağırlıklı puanlamayla birleştirip sinyal üretir
├── backtest.py          # Sinyallere göre pozisyon açıp kapatan backtest motoru
├── main.py               # Komut satırı arayüzü (rapor + grafik)
├── app.py                 # Streamlit web arayüzü
├── requirements.txt
├── pine/
│   └── strategy.pine    # TradingView Pine Script v5 stratejisi
└── README.md
```

---

## 2. VS Code ile Kurulum (Python motoru)

1. **Python'u kurun** (3.10+ önerilir): https://www.python.org/downloads/
   Kurulumda "Add Python to PATH" kutucuğunu işaretleyin.
2. **VS Code'u kurun**: https://code.visualstudio.com/
3. VS Code içinde **Extensions** sekmesinden "Python" (Microsoft) eklentisini kurun.
4. Bu `finans_motoru` klasörünü VS Code'da açın (`File > Open Folder`).
5. VS Code'un içindeki terminali açın (`Terminal > New Terminal`) ve sanal
   ortam oluşturun:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # macOS/Linux:
   source .venv/bin/activate
   ```
6. Gerekli paketleri kurun:
   ```bash
   pip install -r requirements.txt
   ```
7. VS Code sağ alt köşeden Python yorumlayıcısı olarak `.venv` içindekini seçin
   (Command Palette → "Python: Select Interpreter").

### Çalıştırma

```bash
# BIST hissesi, 1 saatlik mumlarla
python main.py --ticker THYAO.IS --interval 1h --plot

# ABD hissesi, 15 dakikalık
python main.py --ticker AAPL --interval 15m --period 30d --plot

# Kripto, günlük
python main.py --ticker BTC-USD --interval 1d --plot

# İnternet olmadan / hızlı deneme (sentetik veri)
python main.py --demo --interval 1d --plot
```

Çıktılar:
- Konsolda son sinyal özeti + backtest metrikleri (JSON)
- `rapor_sinyaller.csv` — tüm barlar için indikatör + sinyal detayları
- `rapor_grafik.png` (yalnızca `--plot` ile) — fiyat, sinyaller, RSI, equity eğrisi

Tüm parametreler için:
```bash
python main.py --help
```

### Zaman Aralıkları

| Kod | Açıklama |
|---|---|
| `1m` | 1 dakikalık (Yahoo: son 7 gün) |
| `5m` | 5 dakikalık (son ~60 gün) |
| `15m` | 15 dakikalık (son ~60 gün) |
| `30m` | 30 dakikalık |
| `60m` / `1h` | 1 saatlik (son ~2 yıl) |
| `1d` | Günlük |
| `1wk` | Haftalık |

**Zaman aralığı önerisi:** THYAO.IS üzerinde yapılan gerçek testlerde motor
**1 saatlik ve özellikle 1 günlük** zaman dilimlerinde anlamlı, pozitif
risk-ayarlı performans (Sharpe > 0, profit factor > 1) gösterdi. **5 ve 15
dakikalık** gibi çok kısa vadelerde ise gürültü ve komisyon etkisi baskın
çıkıp Sharpe negatif kaldı — bu, çoklu-indikatör konfluens sistemlerinde
genel bir sınırlamadır, motora özgü bir hata değil. Bu yüzden motoru asıl
**saatlik/günlük swing-trade** analizinde kullanmanızı, çok kısa vadeli
scalping kararlarında tek başına güvenmemenizi öneririz. Farklı bir hissede
sonuçlar değişebilir; `compare_intervals.py` ile her zaman kendi
sembolünüz için tekrar test edin.

---

## 3. TradingView Pine Editör'de Kullanım

1. https://www.tradingview.com adresine gidin ve bir grafik açın (örn. `BIST:THYAO`, `NASDAQ:AAPL`, `BINANCE:BTCUSDT`).
2. Alt paneldeki **"Pine Editor"** (Pine Editör) sekmesine tıklayın.
3. `pine/strategy.pine` dosyasının tamamını açın, kopyalayın ve Pine Editör'e yapıştırın (mevcut şablon kodunu silip yerine yapıştırın).
4. Üstteki **"Add to Chart"** (Grafiğe Ekle) butonuna basın.
5. Grafikte EMA çizgileri, Bollinger bantları, AL/SAT üçgenleri ve sağ üstte
   canlı bir skor/RSI/sinyal paneli göreceksiniz.
6. **Strateji performansını görmek için:** alt sekmelerden **"Strategy Tester"**
   açın — kazanç oranı, kâr faktörü, maksimum düşüş gibi metrikleri TradingView
   otomatik hesaplar (Python motorundaki `backtest.py` ile aynı mantığın
   TradingView tarafındaki karşılığı).
7. **Alarm kurmak için:** grafikte sağ tık → "Add Alert" → Condition olarak
   "AL Sinyali" veya "SAT Sinyali" seçin; tetiklendiğinde e-posta/mobil bildirim
   veya webhook (örn. kendi botunuza) gönderebilirsiniz.
8. Zaman aralığını değiştirmek için grafiğin üstündeki periyot seçiciden
   5dk / 15dk / 1sa / 1G seçin — script otomatik olarak o zaman diliminin
   verisiyle çalışır (Pine Script'te ayrı kod gerekmez).

Girdi parametrelerini (EMA uzunlukları, RSI eşiği, stop-loss/take-profit yüzdeleri
vb.) sağ üstteki dişli ikonundan (Settings → Inputs) değiştirebilirsiniz.

---

## 4. Sistemin Mantığı (Özet)

Her indikatör -1 (güçlü SAT) ile +1 (güçlü AL) arasında bir alt-skor üretir:

- **EMA(9)/EMA(21) kesişimi** — kısa vadeli trend yönü
- **EMA(50) trend filtresi** — fiyat trend çizgisinin üstünde mi altında mı
- **MACD histogram** — momentum yönü ve ivmesi
- **RSI(14)** — aşırı alım/aşırı satım bölgeleri
- **Bollinger Bantları** — fiyatın bant içindeki konumu (ortalamaya dönüş eğilimi)
- **Stokastik (%K/%D)** — kesişim + aşırı bölge teyidi
- **Hacim** — sinyali güçlendiren/zayıflatan hacim teyidi

Bu alt-skorlar önceden tanımlı ağırlıklarla (`DEFAULT_WEIGHTS` / Pine'da `wEma`, `wRsi`...)
birleştirilip -1..+1 arası bir **toplam skora** dönüştürülür. Skor eşikleri
aşıldığında AL/SAT, kaç indikatörün aynı yönde hemfikir olduğuna göre de bir
**güven yüzdesi (confidence)** hesaplanır. Bu "confluence" (çoklu doğrulama)
yaklaşımı, tek bir indikatöre güvenmekten daha sağlam bir karar desteği sunar
— ama yine de **kesinlik garantisi vermez.**

Ağırlıkları `signal_engine.py` içindeki `DEFAULT_WEIGHTS` sözlüğünden ya da
Pine tarafında `wEma`, `wTrend`, `wMacd`... değişkenlerinden kendi stratejinize
göre değiştirebilirsiniz.

---

## 5. Bu Sistemi Başkalarına Nasıl Sunarız? (Dağıtım Seçenekleri)

Sıradan kullanıcılar için en kolaydan en gelişmişe doğru üç yol:

### A) Web arayüzü (en kolay — kod bilmeyenler için)

1. Terminalde:
   ```bash
   streamlit run app.py
   ```
2. Tarayıcıda `http://localhost:8501` açılır; ticker/interval seçip
   "Analizi Çalıştır" ile herkes kullanabilir.
3. **İnternette paylaşmak için** (ücretsiz):
   - Projeyi bir GitHub reposuna yükleyin.
   - https://share.streamlit.io (Streamlit Community Cloud) üzerinden repoyu
     bağlayın; birkaç dakikada herkesin erişebileceği bir link üretir
     (örn. `https://sizin-app.streamlit.app`).
   - Alternatif: Render.com, Railway.app veya kendi sunucunuzda barındırma.

### B) TradingView üzerinden paylaşım (yatırımcı topluluğu için)

1. `pine/strategy.pine` scriptini Pine Editör'e yapıştırıp kaydedin
   (script adını verin, örn. "Konfluens AL/SAT Motoru").
2. Sağ üstten **"Publish Script"** (Scripti Yayınla) seçeneğiyle:
   - **Public (Herkese Açık)** — TradingView topluluğu görebilir/kullanabilir.
   - **Invite-only (Davetiyeli)** — sadece izin verdiğiniz kullanıcılar
     kullanabilir (ücretli erişim/abonelik modeli kurmak isterseniz bu yol).
3. Yayınladıktan sonra kullanıcılar kendi grafiklerine tek tıkla ekleyebilir.

### C) Bağımsız masaüstü uygulaması (teknik olmayan kullanıcılar için exe/app)

1. `pip install pyinstaller --break-system-packages`
2. `pyinstaller --onefile main.py`
3. `dist/` klasöründe oluşan çalıştırılabilir dosyayı (Windows: `.exe`)
   paylaşın — kullanıcıların Python kurmasına gerek kalmaz.
   (Not: Streamlit tabanlı `app.py` için `pyinstaller` yerine
   [stlite](https://github.com/whitphx/stlite) ya da Docker imajı önerilir.)

### D) API / otomasyon (kendi botunuza entegre etmek isteyenler için)

`signal_engine.compute_signals()` ve `backtest.run_backtest()` fonksiyonları
saf Python fonksiyonlarıdır; bir FastAPI/Flask servisine sarılıp REST API
olarak da sunulabilir, ya da zamanlanmış bir görevle (cron) periyodik olarak
çalıştırılıp sonuçlar Telegram/e-posta ile gönderilebilir. İsterseniz bu
entegrasyonu da ayrıca kurabilirim.

---

## 5b. 1 Saatlik İşlem İçin İleri Seviye Kullanım: Parametre Optimizasyonu ve Çoklu Hisse Tarama

Bu iki araç, motoru "körü körüne varsayılan ayarlarla" değil, geçmiş veriye
göre daha dikkatli ayarlanmış biçimde kullanmak isteyenler içindir.

### `optimize.py` — Walk-Forward Parametre Arama

Belirli bir hissede/zaman aralığında, EMA periyotları, RSI uzunluğu, AL/SAT
eşikleri, trailing-stop çarpanı, stop-loss ve pozisyon büyüklüğü gibi
parametreleri rastgele dener; veriyi 3 ayrı zaman dilimine bölüp her adayın
**üç dilimde de** tutarlı çalışıp çalışmadığını ölçer (tek dönemde "şanslı"
görünen ama başka dönemde çöken parametreleri eler).

```bash
python optimize.py --ticker THYAO.IS --interval 1h --trials 60
```

Çıktı: `en_iyi_parametreler.json` (en tutarlı parametre seti).

> Bu, geçmişte daha tutarlı çalışan parametreyi bulur; **gelecekte de aynı
> performansı vereceğinin garantisi değildir.** Farklı dönemlerde tekrar
> test edilmesi önerilir.

### `screen_tickers.py` — Aynı Kurallarla Çoklu Hisse Karşılaştırma

Aynı zaman aralığı ve (isteğe bağlı olarak `optimize.py` çıktısı) parametre
setiyle birden fazla hisseyi tarar; hangi hissenin geçmişte bu kurallarla
daha istikrarlı sonuç verdiğini karşılaştırmalı bir tabloda gösterir.

```bash
python screen_tickers.py --tickers "THYAO.IS,ASELSAN.IS,SISE.IS,KCHOL.IS,BIMAS.IS" \
    --interval 1h --capital 2000 --params-file en_iyi_parametreler.json
```

Çıktı: `hisse_taramasi.csv` + konsolda sıralı karşılaştırma tablosu.

### `main.py` ile optimize edilmiş parametreleri kullanmak

```bash
python main.py --ticker THYAO.IS --interval 1h --params-file en_iyi_parametreler.json --plot
```

> ⚠️ **Önemli:** Bu üç araç da sadece geçmiş veri üzerinde çalışır. Hiçbiri
> "gelecekte şu kadar kazanırsınız" diye bir tahmin üretmez ve üretemez.
> Amaçları, sistemin geçmişte ne kadar TUTARLI çalıştığını ölçmek ve bu
> bilgiyle daha bilinçli bir karar vermenize yardımcı olmaktır.

---

## 6. Riskler ve Sorumluluk Reddi

- Bu sistem **geçmiş veriye dayalı istatistiksel bir karar destek aracıdır**,
  gelecekteki fiyat hareketlerini garanti etmez.
- Backtest sonuçları (kayma/slippage, likidite, emir gecikmesi gibi gerçek
  piyasa etkilerini tam yansıtmadığından) gerçek işlem performansından farklı
  olabilir.
- Kaldıraçlı/marjinli işlemler ek risk taşır; `--allow-short` bayrağı ve
  stop-loss/take-profit parametrelerini dikkatli seçin.
- Bu bir yatırım danışmanlığı hizmeti değildir; nihai kararlar kullanıcıya aittir.

---

## 7. Sonraki Adımlar İçin Öneriler

- Çoklu zaman dilimi teyidi (örn. 1 saatlikte sinyal + günlükte trend teyidi).
- Farklı varlık sınıfları için ağırlıkları ayrı ayrı optimize etme (grid search /
  walk-forward analiz).
- Telegram/Discord bot entegrasyonu ile sinyal bildirimleri.
- Gerçek zamanlı veri akışı (WebSocket) ile canlı izleme paneli.

İsterseniz bu adımlardan istediğinizi birlikte kurabiliriz — hangisiyle
devam etmek istersiniz?
