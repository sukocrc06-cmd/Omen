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

## 4b. Motor Güncellemeleri (Eylül 2026): ADX rejim filtresi, OBV, HTF teyidi

Python motoruna (`indicators.py` / `signal_engine.py`) beş iyileştirme
eklendi. Hepsi THYAO.IS / 1 saatlik gerçek veriyle (2023-10 .. 2026-09,
6249 bar) ölçüldü:

1. **ADX rejim filtresi** — daha önce hesaplanıp hiç kullanılmayan ADX,
   artık bileşen ağırlıklarını bar bazında ölçekliyor: piyasa yatayken
   (ADX < 18) trend-takip bileşenleri (EMA kesişim, EMA50 filtresi)
   zayıflar; net trend varken (ADX > 28) güçlenir. Bollinger tam tersi
   yönde ölçeklenir (yatayken güçlü, trendliyken zayıf) — çünkü trend
   döneminde fiyat üst/alt banda yaslanıp kalıp yanlış SAT/AL üretebiliyor.
2. **OBV entegrasyonu** — hacim skoru artık sadece anlık hacim oranına değil,
   OBV'nin 5 barlık eğimine de bakıyor (%60/%40 karışım) — tek barlık hacim
   sıçramalarına karşı daha az gürültülü.
3. **RSI skorlaması yumuşatıldı** — eski sabit basamaklı (30/45/55/70 sınırlarında
   ani sıçrayan) skor, aynı mantığı koruyan ama bölge sınırlarında yumuşak
   geçiş yapan lineer enterpolasyona çevrildi (histerezisin gereksiz
   tetiklenmesini azaltır).
4. **Üst zaman dilimi (HTF) trend teyidi — VARSAYILAN KAPALI** — bar
   aralığından otomatik seçilen bir üst zaman diliminin (1 saatlik barlar
   için günlük) EMA(50) trendiyle çelişen sinyalleri bastırma özelliği
   eklendi (`compute_signals(..., htf_confirm=True)`), ANCAK gerçek veriyle
   test edildiğinde günlük EMA(50) çok yavaş/gecikmeli kaldığı için tam
   olarak en kârlı işlemleri (erken trend dönüşlerini) bastırıp Sharpe'ı
   düşürdü — birden fazla dampen gücü ve EMA uzunluğu kombinasyonuyla
   doğrulandı, hepsi kapalı duruma göre daha kötü sonuç verdi. Bu yüzden
   **varsayılan olarak kapalı** bırakıldı; farklı hisse/aralıkta işe
   yarayabileceği için parametre olarak açık tutuldu (`htf_confirm=True`,
   `cfg={"htf_rule": "1D", "htf_ema_len": 50}`).
5. **Yeni `--mode conservative` (muhafazakar) optimizasyon modu** — bkz.
   aşağıdaki 5b ve 5d.

**Ölçülen etki (THYAO.IS / 1h, aynı eski parametrelerle, sadece motor
değişikliği):**

| | Eski motor | Yeni motor (ADX+OBV+RSI, HTF kapalı) |
|---|---|---|
| Sharpe (yıllıklandırılmış) | 0.27 | 0.70 |
| Max düşüş | -%23.6 | -%5.1 |
| Profit factor | 1.07 | 1.17 |
| Kazanma oranı | %34.4 | %37.4 |

Parametreler de yeni motora göre yeniden optimize edildiğinde (bkz. 5b)
Sharpe 1.2'ye, max düşüş -%3'e kadar iyileşiyor. Bu geçmiş veridir,
gelecekte aynı sonucu garanti etmez — ama yön net: **risk (özellikle
max düşüş) belirgin şekilde azaldı.**

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

Üç mod vardır (`--mode`):
- **`robust`** (varsayılan) — tutarlılığı (ortalama Sharpe eksi bölümler arası
  sapma) maksimize eder.
- **`trend`** — çıkışları kasıtlı gevşetip büyük trendleri daha çok yakalamayı
  hedefler; karşılığında daha büyük düşüşlere (drawdown) açıktır.
- **`conservative`** (muhafazakar) — en yüksek getiriyi DEĞİL, en düşük düşüş +
  en tutarlı Sharpe kombinasyonunu arar (küçük pozisyon büyüklüğü, dar
  stop-loss, sadece güçlü confluence'ta giriş). Çıktısı
  `en_iyi_parametreler_muhafazakar.json`. Bkz. 5d.

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

## 5c. Telegram / E-posta Bildirimleri

Sinyal DEĞİŞTİĞİNDE (ör. BEKLE -> AL) telefonuna Telegram mesajı ve/veya
mailine e-posta gönderen `notify.py` scripti. Sinyal aynı kaldığı sürece
tekrar tekrar bildirim göndermez.

### Kurulum (Telegram - 5 dakika)

1. Telegram'da **BotFather** ile konuş (arama kutusuna "BotFather" yaz).
2. `/newbot` yaz, botuna bir isim ver. Sana bir **bot token** verecek
   (örn. `123456789:ABCdefGhIJKlmNoPQRstuVwxyZ`).
3. Oluşturduğun bota Telegram'dan bir mesaj gönder (örn. "merhaba") - bu
   önemli, botun sana mesaj atabilmesi için önce senin ona yazman gerekiyor.
4. Tarayıcıda şunu aç (TOKEN kısmını kendi tokenınla değiştir):
   `https://api.telegram.org/botTOKEN/getUpdates`
   Dönen metinde `"chat":{"id":123456789,...}` gibi bir sayı arayın - bu sizin
   **chat_id**'inizdir.
5. `notify_config.example.json` dosyasını kopyalayıp `notify_config.json`
   adıyla kaydedin, `bot_token` ve `chat_id` alanlarını doldurun.
   (`notify_config.json` `.gitignore`'da - GitHub'a asla yüklenmez.)

Test:
```bash
python notify.py --ticker THYAO.IS --interval 1h --config notify_config.json --test
```
`--test` her durumda bildirim gönderir (bağlantıyı doğrulamak için). Gerçek
kullanımda `--test` OLMADAN çalıştırın - o zaman sadece sinyal değiştiğinde
bildirim gelir.

**Birden fazla hisseyi tek çalıştırmada takip etmek** için `--tickers`
(virgülle ayrılmış) kullanın - her hisse kendi durumunu ayrı dosyada tutar,
sinyali değişen HER hisse için ayrı bildirim gider:
```bash
python notify.py --tickers "THYAO.IS,ASELS.IS,SISE.IS,KCHOL.IS,BIMAS.IS" --interval 1h \
    --config notify_config.json --params-file en_iyi_parametreler_orta.json
```

### Kurulum (E-posta - opsiyonel)

Gmail kullanıyorsanız normal şifreniz çalışmaz; **Uygulama Şifresi** (App
Password) oluşturmanız gerekir: Google Hesabı → Güvenlik → 2 Adımlı Doğrulama
(açık olmalı) → Uygulama Şifreleri. `notify_config.json` içinde
`email.enabled` değerini `true` yapıp bilgileri doldurun.

### Otomatik çalıştırma (Windows Görev Zamanlayıcı)

`notify.py` kendi kendine periyodik çalışmaz - Windows'un **Görev
Zamanlayıcı**sı (Task Scheduler) ile her saat başı tetiklenmesi gerekir:

1. Başlat menüsünden "Görev Zamanlayıcı" (Task Scheduler) açın.
2. Sağdan **Temel Görev Oluştur** (Create Basic Task) tıklayın.
3. İsim verin (ör. "Finans Motoru Bildirim"), **Günlük** (Daily) seçin.
4. Tekrar aralığını her gün, ardından görev özelliklerinden **Tetikleyiciler**
   (Triggers) sekmesinde "Görevi her şu kadar sürede bir tekrarla" (Repeat
   task every) = **1 saat**, süre = **Süresiz** (Indefinitely) olarak ayarlayın.
5. **Eylem** (Action) = "Bir programı başlat" (Start a program):
   - Program/script: `C:\Users\sukru\OneDrive\Desktop\Omen\finans_motoru\.venv\Scripts\python.exe`
     (venv'in tam yolu; `py` yerine venv'in python.exe'sini kullanmak daha güvenilirdir)
   - Bağımsız değişkenler (Arguments) - tek hisse:
     `notify.py --ticker THYAO.IS --interval 1h --config notify_config.json --params-file en_iyi_parametreler.json`
   - Bağımsız değişkenler (Arguments) - birden fazla hisse (bkz. 5c):
     `notify.py --tickers "THYAO.IS,ASELS.IS,SISE.IS,KCHOL.IS,BIMAS.IS" --interval 1h --config notify_config.json --params-file en_iyi_parametreler_orta.json`
   - Başlangıç konumu (Start in): `C:\Users\sukru\OneDrive\Desktop\Omen\finans_motoru`
6. Kaydedin. İsterseniz görevi sağ tıklayıp **Çalıştır** (Run) ile hemen test edin.

> ⚠️ BIST piyasası kapalıyken (akşam/hafta sonu) veri değişmeyeceği için
> gereksiz sorgu yapmamak isterseniz görevi sadece işlem saatlerinde (ör.
> 10:00-18:00, Pazartesi-Cuma) çalışacak şekilde de sınırlandırabilirsiniz
> (Tetikleyiciler sekmesinde "Başlangıç" ve "Bitiş" saatleri girilebilir).

---

## 5d. "Az Kazanç, Sürekli Birikim" — 50.000 TL için Muhafazakar Mod

Bu bölüm, büyük getiri değil **düşük ama istikrarlı, yıllar içinde biriken**
kazanç hedefleyen kullanıcılar için `--mode conservative` çıktısının nasıl
kullanılacağını ve gerçek veriyle ölçülen sonuçları özetler. Bu bir yatırım
tavsiyesi değildir — sadece motorun bu risk profiline göre nasıl
ayarlanacağını gösterir.

### Ne değişiyor?

`en_iyi_parametreler_muhafazakar.json` (robust/trend'e göre):
- **Pozisyon büyüklüğü küçük** (~%8-15, robust'ta %15-25) — tek işlemin
  sermayeye etkisi sınırlı kalır.
- **Giriş eşiği yüksek** (buy_th 0.3-0.4, robust'ta 0.2-0.3) — sadece güçlü
  confluence'ta (çoğu indikatör aynı yönde hemfikirken) işleme girilir, daha
  az ama daha "temiz" sinyal.
- **Dar stop-loss / trailing** — kayıplar erken kesilir, kârlar erken
  kilitlenir; büyük trendleri sonuna kadar takip etmek yerine güvenlik
  önceliklidir.

### Gerçek veriyle ölçülen sonuç (2023-10 .. 2026-09, ~2.9 yıl, 50.000 TL)

```bash
python main.py --ticker THYAO.IS --interval 1h --capital 50000 \
    --params-file en_iyi_parametreler_muhafazakar.json
```

| Hisse | Sonuç bakiye | Getiri | Max düşüş | Sharpe | İşlem sayısı | Kazanma oranı |
|---|---|---|---|---|---|---|
| THYAO.IS | 51.407 TL | +%2.81 | **-%1.5** | 1.14 | 149 | %36.2 |
| ASELS.IS (aynı parametreler, ayrı optimize edilmeden) | 58.098 TL | +%16.2 | -%3.9 | 4.09 | 146 | %39.0 |

ASELS.IS satırı THYAO için bulunan parametrelerle çalıştırıldı (yeniden
optimize edilmedi) — amaç, ayarların tek hisseye "ezberlenmediğini" kabaca
görmekti. Sonuçlar hisseye göre büyük fark gösterebilir; her zaman kendi
sembolünüzle `optimize.py --mode conservative` çalıştırın.

**Yorum:** ~%1-6/yıl aralığında, ama tek haneli düşüklükte düşüşle (drawdown)
—yani "büyük kazanç" değil, "küçük ama nispeten sindirilebilir kayıp riskiyle
yavaş birikim" profili. Bu, isteğinizle (az kazanç + süreklilik) örtüşüyor.

### Pratik öneriler (50.000 TL için)

1. **Tek hisseye yatırmayın.** `screen_tickers.py` ile 4-5 farklı BIST hissesinde
   (`--params-file en_iyi_parametreler_muhafazakar.json`) ayrı ayrı test edip
   sermayeyi birkaçına bölmek, tek bir hissenin kötü bir döneminin tüm
   sermayeyi etkilemesini azaltır.
2. **`rolling_windows.py` ile dağılıma bakın**, tek bir backtest sonucuna değil
   — "ortalama ne olurdu" değil "en kötü pencerede ne olurdu" sorusuna cevap
   arayın (bkz. `THYAO_IS_pencere_analizi.csv` örneği).
3. **Periyodik olarak yeniden optimize edin** (ör. 3-6 ayda bir) — piyasa
   rejimi değiştikçe (bkz. 4b'deki chunk bazlı Sharpe'ların son dönemde
   düşme eğilimi) sabit parametreler zamanla eskiyebilir.
4. **`notify.py` + Görev Zamanlayıcı** ile sinyalleri takip edin ama işlemleri
   MANUEL onaylayın — bu araç otomatik emir göndermez, sadece bildirir; son
   kararı siz verirsiniz.
5. Bu motor bir **yatırım danışmanı değildir**; "az kazanç + süreklilik"
   hedefi geçmiş veride gözlemlendi, gelecekte garanti değildir. Gerçek
   parayla başlamadan önce mutlaka demo/kağıt hesapta birkaç ay izleyin.

---

## 5e. "Orta" Profil: Trend Modunun Çıkış Mantığı + Küçük Pozisyon

`--mode conservative` ve `--mode robust`'ın karşılaştırmasında robust modun
Sharpe/CAGR açısından beklenenden zayıf kaldığı görüldü. Nedeni araştırıldığında
asıl fark **pozisyon büyüklüğü değil, çıkış mantığıydı**: trend modun geniş
trailing-stop'u (`trailing_atr_mult=6.0`) ve sert-eşikli çıkışı (`sell_th=-0.45`)
kârı erken kesmek yerine trendi sonuna kadar takip ediyor.

`en_iyi_parametreler_orta.json`, trend modun bulduğu indikatör/çıkış
parametrelerini aynen kullanıp **sadece pozisyon büyüklüğünü %40'tan %15'e**
düşürür (position sizing ile getiri/düşüş neredeyse doğrusal ölçekleniyor,
Sharpe/kazanma oranı/işlem zamanlaması DEĞİŞMİYOR - bkz. aşağıdaki tablo).

```bash
python main.py --ticker THYAO.IS --interval 1h --capital 50000 \
    --params-file en_iyi_parametreler_orta.json
```

**THYAO.IS / ASELS.IS, 2023-10-12 .. 2026-09-01 (~2.89 yıl), 50.000 TL:**

| Mod | THYAO CAGR | THYAO max düşüş | THYAO Sharpe | ASELS CAGR | ASELS max düşüş |
|---|---|---|---|---|---|
| conservative (%8 pozisyon) | %0.96 | -%1.5 | 1.14 | %5.34 | -%3.89 |
| robust (%15 pozisyon, orijinal çıkış) | %1.73 | -%2.96 | 1.20 | %8.53 | -%4.85 |
| **orta (trend çıkışı + %15 pozisyon)** | **%2.74** | **-%3.29** | **1.54** | **%9.52** | **-%7.18** |
| trend (%40 pozisyon, orijinal) | %7.05 | -%8.6 | 1.54 | %25.87 | -%17.83 |

"Orta" profil, robust moddan hem daha yüksek Sharpe hem daha yüksek CAGR
veriyor - biraz daha yüksek (ama hâlâ tek haneli) bir düşüş karşılığında.
Pozisyon büyüklüğü `position_size_pct` alanından elle %10-%25 arasında
ayarlanıp kendi risk toleransınıza göre bu doğrusal ölçeklemeden
yararlanabilirsiniz (bkz. tablo yukarıdaki bölümlerde farklı yüzdeler için).

> Bu üçü de (conservative/robust/orta/trend) aynı geçmiş veri üzerinde
> ölçüldü; hiçbiri gelecekteki performansı garanti etmez ve hiçbiri
> Türk Lirası enflasyonuna karşı bir koruma sağlamaz (bkz. 5d'deki
> enflasyon notu).

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
