# Pine Script Stratejisi: Çoklu Zaman Dilimi Teyidi + Filtre Katmanları

**Tarih:** 2026-08-26
**Kapsam:** `finans_motoru/pine/strategy.pine`
**Hedef kullanım:** BIST hisseleri, saatlik (1s) grafik, long-only

## Amaç ve Kapsam Dışı

Mevcut `strategy.pine` dosyası (EMA/RSI/MACD/BB/Stokastik/Hacim ağırlıklı
konfluens skorlaması) TradingView Pine Editör'de çalışıyor ve AL/SAT/GÜÇLÜ
AL/GÜÇLÜ SAT sinyalleri üretiyor. README'nin kendi geçmiş testleri, sistemin
**1 saatlik ve günlük** zaman dilimlerinde 5-15 dakikalığa göre daha tutarlı
(Sharpe > 0, profit factor > 1) çalıştığını gösteriyor.

Bu spec'in amacı, sistemi "kusursuz" hale getirmek DEĞİL (hiçbir gösterge
kombinasyonu gelecekteki fiyatı garanti edemez) — bunun yerine **geçmiş
veride ölçülebilir şekilde daha tutarlı, yanlış sinyal oranı daha düşük**
bir hale getirmektir. Çekirdek ağırlıklı skorlama mantığı değişmez; üstüne
bağımsız, açılıp kapanabilir 3 filtre/risk katmanı eklenir.

**Kapsam dışı:** Açığa satış (short) desteği (BIST'te pratik değil), haftalık
teyit katmanı, diverjans tespiti, hacim profili — bunlar ayrı bir iterasyonda
değerlendirilebilir.

## Mevcut Durum (Baseline)

- Tek zaman dilimli: script hangi periyotta çalıştırılırsa (5dk/1s/1g...)
  yalnızca o periyodun verisiyle skor üretir, üst zaman dilimi teyidi yok.
- ADX / trend gücü filtresi yok (Python tarafında `indicators.py` içinde var
  ama Pine'a hiç taşınmamış).
- Sinyal soğuma (cooldown) yok — ardışık ters sinyaller (whipsaw) komisyonla
  hesabı eritebilir.
- Stop-loss/take-profit sabit yüzde (`slPct=3%`, `tpPct=6%`) — oynaklığı
  farklı hisselere (THYAO vs. BIMAS) aynı şekilde uygulanıyor.

## Yeni Katmanlar

Üç katman da bağımsız `input.bool`/`input.string` anahtarlarıyla açılıp
kapatılabilir olacak. Tüm anahtarlar **varsayılan olarak açık**. Anahtarların
hepsi kapatıldığında (ve `slMode="Sabit %"` seçildiğinde) script **mevcut
davranışla birebir aynı** sinyalleri üretmelidir — bu, regresyon güvencesidir.

### 1. Günlük Trend Teyidi (yumuşak mod)

- `request.security()` ile günlük kapanış ve günlük EMA50 çekilir
  (`lookahead=barmerge.lookahead_off` — ileri-bakış/repaint riskini önlemek
  için zorunlu).
- `scoreDailyTrend = dailyClose > dailyEma50 ? 1.0 : dailyClose < dailyEma50 ? -1.0 : 0.0`
- Mevcut 7 alt-skorun yanına **8. ağırlıklı bileşen** olarak eklenir:
  `wDailyTrend = 0.9` (saatlik `wTrend=0.8`'den biraz daha otoriter, çünkü
  üst zaman dilimi daha güvenilir kabul edilir).
- **Yumuşak mod**: günlük trend ters yönlü olduğunda sinyali tamamen
  engellemez, sadece toplam ağırlıklı skoru aşağı/yukarı çeker — mevcut
  ağırlıklı ortalama mimarisiyle birebir tutarlı bir mekanizma.
- Input: `useDailyTrend` (bool, varsayılan `true`), `dailyEmaLen` (int,
  varsayılan 50).

### 2. ADX Trend Gücü Filtresi (katı gate, sadece yeni girişlerde)

- `ta.adx()` hesaplanır (`adxLen` varsayılan 14, `adxThreshold` varsayılan
  **20** — kullanıcı onayıyla sabitlendi).
- ADX eşiğin altındaysa (yatay/gürültülü piyasa) **yeni AL girişi açılmaz**:
  `isBuy := isBuy and (not useAdxFilter or adx >= adxThreshold)`.
- Mevcut pozisyondan **çıkış (SAT) bu filtreden etkilenmez** — yatay
  piyasada bile güvenli çıkışa her zaman izin verilir.
- Input: `useAdxFilter` (bool, varsayılan `true`), `adxLen` (int, varsayılan
  14), `adxThreshold` (float, varsayılan 20).

### 3. Sinyal Soğuma + ATR Bazlı Risk Yönetimi

- **Soğuma:** Son sinyal değişiminden itibaren `cooldownBars` (int,
  varsayılan 3) bar geçmeden ters yönde yeni giriş açılmaz. Son sinyal
  değişiminin bar index'i `var int` ile tutulur.
- Input: `useCooldown` (bool, varsayılan `true`), `cooldownBars` (int,
  varsayılan 3).
- **ATR bazlı SL/TP:** Risk grubuna `slMode` seçimi eklenir
  (`input.string`, seçenekler `"Sabit %"` / `"ATR Bazlı"`, varsayılan
  **"ATR Bazlı"**).
  - `"Sabit %"` modunda mevcut `slPct`/`tpPct` davranışı korunur (geriye
    dönük uyumluluk).
  - `"ATR Bazlı"` modunda: `atr = ta.atr(atrLen)` (varsayılan 14),
    `slPrice = avgPrice - atrMultSL * atr` (varsayılan çarpan 1.5),
    `tpPrice = avgPrice + atrMultTP * atr` (varsayılan çarpan 3.0).

## Bilgi Paneli Güncellemesi

Mevcut skor/RSI/sinyal tablosuna iki satır eklenir: **Günlük Trend**
(YUKARI/AŞAĞI/NÖTR) ve **ADX** değeri — kullanıcı hangi filtrenin sinyali
neden güçlendirdiğini/engellediğini grafik üzerinde görebilsin diye.

## Hata Yönetimi / Kenar Durumları

- İlk barlarda (yeterli geçmiş veri birikmeden) ADX/ATR `na` dönebilir —
  bu durumlarda ilgili filtre/risk hesaplaması pas geçilir (varsayılan
  davranışa düşer, script hata vermez).
- `request.security()` çağrısı repaint riskini önlemek için
  `lookahead=barmerge.lookahead_off` ile yapılır ve günlük bar henüz
  kapanmadan sinyale dahil edilmez.
- Bollinger genişliği sıfır olma durumu zaten mevcut kodda ele alınmış
  (`bbWidth != 0 ? ... : 0.0`), değişmiyor.

## Doğrulama Planı

Pine Script yerel olarak derlenemediği için (yalnızca TradingView Pine
Editör'de çalışır) doğrulama şu adımlarla yapılacak:

1. **Söz dizimi kontrolü:** Kod TradingView Pine Editör'e yapıştırılıp
   "Add to Chart" ile derlenecek; hata çıkarsa düzeltilecek.
2. **Regresyon kontrolü:** Tüm yeni filtreler kapatılıp `slMode="Sabit %"`
   seçildiğinde script eskisiyle birebir aynı sinyalleri üretmeli.
3. **Önce/sonra karşılaştırması:** THYAO.IS 1 saatlik grafikte Strategy
   Tester filtreler kapalı/açık haliyle çalıştırılıp Net Kâr / Kazanma
   Oranı / Kâr Faktörü / Maks. Düşüş karşılaştırılacak. Sonuçlara göre
   eşikler (ADX 20, cooldown 3 bar, ATR çarpanları) ince ayar yapılabilir.
4. **README güncellemesi:** Yeni parametreler ve önce/sonra test adımları
   README'nin Pine bölümüne eklenecek.

## Geriye Dönük Uyumluluk

Tüm yeni davranış opsiyonel giriş parametreleriyle kontrol edilir ve
varsayılanları makul biçimde açık bırakılır; ancak hepsi kapatıldığında
sistem tam olarak eski haline döner. Python motoru (`signal_engine.py`,
`backtest.py`, `optimize.py` vb.) bu değişiklikten etkilenmez — kapsam
yalnızca `pine/strategy.pine` dosyasıdır.
