# OptiTrade Analiz Modelleri Detaylı Dokümantasyon

Bu doküman, OptiTrade platformunda kullanılan finansal analiz modellerini, amaçlarını, temel parametrelerini ve skorlarının nasıl yorumlanması gerektiğini detaylandırmaktadır.

---

## 1. Piyasa Rejimi Sınıflandırıcısı (MarketConditionClassifier)

*   **Amaç:** Mevcut piyasa koşullarını (güçlü boğa trendi, zayıf ayı trendi, yatay piyasa vb.) sınıflandırmak. Bu sınıflandırma, diğer modellerin ağırlıklandırılmasında kullanılır.
*   **Temel Parametreler:**
    *   `adx_window`: ADX göstergesinin hesaplandığı pencere boyutu (varsayılan: 14).
    *   `adx_threshold`: Bir trendin güçlü kabul edilmesi için ADX değeri eşiği (varsayılan: 25).
*   **Skor Yorumu:** Bu model doğrudan bir al/sat skoru üretmez. Bunun yerine, piyasa rejimini belirten bir `regime` değeri döndürür. Skor değeri her zaman 0.0'dır.
*   **Özel Hususlar:** Diğer modellerin ağırlıklarını dinamik olarak ayarlamak için kritik bir öneme sahiptir.

---

## 2. Fiyat Trendi Modeli (PriceTrendModel)

*   **Amaç:** RSI, MACD, SMA ve ADX gibi teknik göstergeleri kullanarak fiyat trendinin yönünü ve gücünü belirlemek.
*   **Temel Parametreler:**
    *   `rsi_window`: RSI periyodu (varsayılan: 14).
    *   `macd_fast`, `macd_slow`, `macd_sign`: MACD göstergesi için pencere boyutları.
    *   `sma_short`, `sma_long`: Kısa ve uzun vadeli Basit Hareketli Ortalamalar için pencere boyutları.
    *   `adx_window`: ADX periyodu.
*   **Skor Yorumu:** -1.0 (Güçlü Sat) ile +1.0 (Güçlü Al) arasında bir skor üretir. Pozitif skor yükseliş trendini, negatif skor düşüş trendini gösterir.

---

## 3. Hacim Artışı Modeli (VolumeSurgeModel)

*   **Amaç:** Hacimdeki anormal artışları veya azalışları ve bunların fiyat üzerindeki potansiyel etkilerini analiz etmek.
*   **Temel Parametreler:**
    *   `volume_ma_window`: Hacim hareketli ortalaması için pencere boyutu.
    *   `deviation_scale`: Hacim sapmasının skora etkisini ölçeklendiren faktör.
    *   `obv_influence`: OBV (On-Balance Volume) trendinin skora katkısı.
*   **Skor Yorumu:** -1.0 (Güçlü Sat) ile +1.0 (Güçlü Al) arasında bir skor üretir. Yüksek pozitif skorlar hacim destekli yükseliş potansiyelini, yüksek negatif skorlar ise hacim destekli düşüş potansiyelini gösterir.

---

## 4. Haber Duyarlılığı Modeli (NewsSentimentModel)

*   **Amaç:** Finansal haber başlıklarının duyarlılık analizini yaparak piyasa üzerindeki potansiyel etkisini ölçmek.
*   **Temel Parametreler:**
    *   `limit`: Analiz edilecek haber başlığı sayısı (varsayılan: 20).
*   **Skor Yorumu:** -1.0 (Çok Negatif) ile +1.0 (Çok Pozitif) arasında bir skor üretir. Pozitif skorlar olumlu haber akışını, negatif skorlar olumsuz haber akışını gösterir.
*   **Özel Hususlar:** `DataFetcher` aracılığıyla haber başlıklarını çeker. FinBERT gibi önceden eğitilmiş bir duyarlılık analiz modeli kullanır.

---

## 5. Sosyal Medya Duyarlılığı Modeli (SocialSentimentModel)

*   **Amaç:** Sosyal medya (örneğin Reddit) gönderilerinin duyarlılık analizini yaparak piyasa üzerindeki potansiyel etkisini ölçmek.
*   **Temel Parametreler:**
    *   `limit`: Analiz edilecek sosyal medya gönderisi sayısı (varsayılan: 25).
*   **Skor Yorumu:** -1.0 (Çok Negatif) ile +1.0 (Çok Pozitif) arasında bir skor üretir. Pozitif skorlar olumlu sosyal medya algısını, negatif skorlar olumsuz sosyal medya algısını gösterir.
*   **Özel Hususlar:** `DataFetcher` aracılığıyla sosyal medya gönderilerini çeker. FinBERT gibi önceden eğitilmiş bir duyarlılık analiz modeli kullanır.

---

## 6. Destek/Direnç Modeli (SupportResistanceModel)

*   **Amaç:** Fiyat grafiğindeki önemli destek ve direnç seviyelerini belirlemek ve mevcut fiyatın bu seviyelere yakınlığına göre skor üretmek.
*   **Temel Parametreler:**
    *   `order`: Fraktal tespiti için pencere boyutu (varsayılan: 2).
    *   `tolerance`: Fiyatın destek/direnç seviyesine ne kadar yakın olması gerektiğini belirten yüzde tabanlı tolerans (varsayılan: 0.01).
    *   `atr_tolerance_multiplier`: ATR tabanlı dinamik tolerans hesaplaması için çarpan (varsayılan: 1.5). Model, piyasa oynaklığına göre dinamik tolerans kullanır.
*   **Skor Yorumu:** -1.0 (Güçlü Sat) ile +1.0 (Güçlü Al) arasında bir skor üretir. Fiyatın desteğe yakın olması pozitif, dirence yakın olması negatif skor üretir.

---

## 7. Uyumsuzluk Tespit Modeli (DivergenceDetectionModel)

*   **Amaç:** Fiyat hareketi ile RSI gibi momentum göstergeleri arasındaki uyumsuzlukları (diverjansları) tespit etmek. Bu uyumsuzluklar genellikle trend dönüşlerinin habercisi olabilir.
*   **Temel Parametreler:**
    *   `rsi_window`: RSI periyodu (varsayılan: 14).
    *   `extrema_order`: Yerel ekstremumları (zirve/dip) bulmak için kullanılan pencere boyutu.
    *   `lookback_period`: Uyumsuzluk aramak için geçmişe dönük veri periyodu.
*   **Skor Yorumu:** -1.0 (Ayı Uyumsuzluğu) ile +1.0 (Boğa Uyumsuzluğu) arasında bir skor üretir. Boğa uyumsuzluğu pozitif, ayı uyumsuzluğu negatif skor verir.

---

## 8. Formasyon Tespit Modeli (FormationDetectionModel)

*   **Amaç:** Fiyat grafiğindeki klasik teknik analiz formasyonlarını (Omuz-Baş-Omuz, Üçgenler, Çift Tepe/Dip vb.) tespit etmek.
*   **Temel Parametreler:**
    *   `extrema_order`: Yerel ekstremumları bulmak için pencere boyutu.
    *   `tolerance`: Formasyon tespiti için fiyat sapması toleransı.
    *   `required_data_points`: Modelin çalışması için gereken minimum veri noktası sayısı.
*   **Skor Yorumu:** -1.0 (Düşüş Formasyonu) ile +1.0 (Yükseliş Formasyonu) arasında bir skor üretir. Formasyonun türüne göre skor ve detay bilgisi döndürür. Formasyon tespit edilmezse veya kırılma bekleniyorsa 0.0 skor verir.

---

## 9. Finansal Oran Modeli (FinancialRatioModel)

*   **Amaç:** Hisse senetleri için temel finansal oranları (F/K, PD/DD, Borç/Özkaynak vb.) analiz ederek bir skor üretmek.
*   **Temel Parametreler:** Yok (oranlar doğrudan `yfinance`'dan çekilir).
*   **Skor Yorumu:** -1.0 (Zayıf Temel) ile +1.0 (Güçlü Temel) arasında bir skor üretir. Oranların sektör ortalamalarına veya tarihsel verilere göre iyi veya kötü olmasına bağlı olarak skor verir.
*   **Özel Hususlar:** **Sadece hisse senetleri için geçerlidir.** Kripto para birimleri için çalıştırılmaz ve 0.0 skor döndürür.

---

## 10. Makine Öğrenmesi Modeli (MachineLearningModel)

*   **Amaç:** Geçmiş verilere dayalı olarak gelecekteki fiyat hareketini tahmin etmek için XGBoost gibi makine öğrenmesi algoritmalarını kullanmak.
*   **Temel Parametreler:** Modelin eğitim sırasında belirlenen hiperparametreleri ve özellikleri kullanır.
*   **Skor Yorumu:** -1.0 (Düşüş Tahmini) ile +1.0 (Yükseliş Tahmini) arasında bir skor üretir. Modelin tahmin güvenine göre skor verir.
*   **Özel Hususlar:** Her analiz periyodu ve varlık için ayrı ayrı eğitilmesi gerekir.

---

## 11. Makroekonomi Modeli (MacroEconomicModel)

*   **Amaç:** Enflasyon, faiz oranları, GSYİH gibi makroekonomik göstergelerin piyasa üzerindeki etkisini analiz etmek.
*   **Temel Parametreler:** Yok (genellikle harici API'lerden veri çeker).
*   **Skor Yorumu:** -1.0 (Negatif Etki) ile +1.0 (Pozitif Etki) arasında bir skor üretir. Makroekonomik verilerin piyasa duyarlılığı üzerindeki etkisine göre skor verir.

---

## 12. On-Chain Veri Modeli (OnChainModel)

*   **Amaç:** Kripto para birimleri için blok zinciri üzerindeki verileri (işlem hacmi, aktif adresler, borsa giriş/çıkışları vb.) analiz ederek sinyal üretmek.
*   **Temel Parametreler:**
    *   `short_window`, `long_window`: Hareketli ortalama pencereleri.
*   **Skor Yorumu:** -1.0 (Ayı Sinyali) ile +1.0 (Boğa Sinyali) arasında bir skor üretir. On-chain verilerdeki anormalliklere veya trendlere göre skor verir.
*   **Özel Hususlar:** **Sadece kripto para birimleri için geçerlidir.**

---

## 13. Korelasyon Modeli (CorrelationModel)

*   **Amaç:** Farklı varlıklar arasındaki korelasyonu analiz ederek portföy çeşitlendirmesi veya risk yönetimi için bilgi sağlamak.
*   **Temel Parametreler:**
    *   `window`: Korelasyon hesaplaması için pencere boyutu.
    *   `assets`: Karşılaştırılacak varlıkların listesi.
*   **Skor Yorumu:** -1.0 (Negatif Korelasyon) ile +1.0 (Pozitif Korelasyon) arasında bir skor üretir. Genellikle diğer modellerle birlikte kullanılır ve doğrudan al/sat sinyali üretmez.

---

## 14. Temettü İskonto Modeli (DCFModel)

*   **Amaç:** Temettü ödeyen hisse senetlerinin içsel değerini, gelecekteki temettü akışlarını iskonto ederek tahmin etmek.
*   **Temel Parametreler:**
    *   `growth_rate`: Temettü büyüme oranı.
    *   `required_rate_of_return`: Gerekli getiri oranı.
*   **Skor Yorumu:** Tahmin edilen içsel değerin mevcut piyasa fiyatına göre düşük veya yüksek olmasına bağlı olarak bir skor üretir. Pozitif skor, hissenin değerinin altında işlem gördüğünü gösterir.
*   **Özel Hususlar:** **Sadece temettü ödeyen hisse senetleri için geçerlidir.**
