# OptiTrade Tahmin Modeli Geliştirme - Yapılacaklar Listesi

Bu liste, OptiTrade projesinin gelecekteki geliştirme alanlarını ve iyileştirme hedeflerini içermektedir.

## Mevcut Durum ve Sonraki Adımlar:

### Önemli Hatırlatma: Model Parametre Optimizasyonu

Modellerimiz artık farklı zaman aralıklarında (15m, 4h, 1d) veri çekip analiz yapabilmektedir. Ancak, kural tabanlı modellerin iç parametreleri (pencere boyutları, toleranslar vb.) ve Makine Öğrenmesi modelinin özellikleri/hiperparametreleri şu anda **günlük (1d) verilere göre heuristik olarak ölçeklendirilmiştir**. Bu, modellerin farklı aralıklarda çalışmasını sağlasa da, o aralık için **en iyi performansı garanti etmez**.

**Gerçek optimizasyon için:** Her bir zaman aralığı (15m, 4h, 1d) için her bir modelin parametrelerinin (ve ML modeli için özellik mühendisliği ile hiperparametrelerin) özel olarak ayarlanması ve eğitilmesi gerekmektedir. Bu, genellikle kapsamlı bir geriye dönük test çerçevesi ve/veya gelişmiş optimizasyon algoritmaları gerektiren, uzun soluklu bir araştırma ve geliştirme sürecidir.

### Geliştirme Alanları:

1.  **Hisse Senedi Analizi Entegrasyonu:** OptiTrade modelinin kripto varlıklara ek olarak hisse senetlerini de analiz edebilmesi için gerekli entegrasyonlar yapılacaktır.
    *   **Frontend UI Geliştirmesi:** Kullanıcının 'Kripto' veya 'Hisse Senedi' olarak varlık tipini seçebileceği bir arayüz eklenecektir.
        - **(Tamamlandı: Varlık Tipi Seçimi UI)** Frontend'e varlık tipi seçimi (Kripto/Hisse Senedi) için UI eklendi.
        - **(Tamamlandı: API Entegrasyonu)** `fetchData` fonksiyonu, `assetType` parametresini API çağrılarına dahil edecek şekilde güncellendi.
    *   **(Tamamlandı) Backend API Güncellemesi:** API, varlık tipini (örn: `asset_type=crypto` veya `asset_type=stock`) kabul edecek şekilde güncellendi.
    *   **Hisse Senedi Veri Çekimi:** Hisse senetlerine özgü veriler (bilanço, gelir tablosu, nakit akış tablosu, temel oranlar vb.) için yeni veri çekme mekanizmaları entegre edilecektir.
        - **(Tamamlandı: Finansal Tablo Veri Çekimi)** `DataFetcher`'a `yfinance` üzerinden gelir tablosu, bilanço ve nakit akış tablosu verilerini çekme ve önbelleğe alma yeteneği eklendi.
    *   **Hisse Senedi Modelleri/Faktörleri:** Hisse senetlerine özgü finansal faktörleri (örn: F/K oranı, defter değeri, borç/özkaynak oranı) analiz eden yeni modeller geliştirilecek veya mevcut modeller bu faktörleri içerecek şekilde adapte edilecektir.
        - **(Tamamlandı: FinancialRatioModel Oluşturuldu ve Genişletildi)** Hisse senetleri için F/K (P/E), P/B (P/B), Borç/Özkaynak (D/E), Yıllık EPS Büyümesi, Fiyat/Satış (P/S) ve FAVÖK Marjı oranlarını hesaplayan ve buna göre bir skor üreten `FinancialRatioModel` oluşturuldu.
    *   **(Tamamlandı: Hisse Senedi Ağırlık Optimizasyonu)** `ScoringEngine` ve `config.py`, hisse senetleri için ayrı model ağırlık profilleri kullanacak şekilde güncellendi. Bu sayede, `FinancialRatioModel` gibi temel analiz modellerine daha fazla önem verilirken, `OnChainModel` gibi ilgisiz modeller devre dışı bırakıldı.

## Gelecek Planları ve Fikirler

-   [x] **Derinlemesine Hisse Senedi Analizi:**
    -   [x] **İndirgenmiş Nakit Akışları (DCF) Modeli:** Şirketler için gerçeğe uygun değer hesaplaması yapacak yeni bir model eklendi.
    -   [ ] **Temettü İskonto Modeli (DDM):** Özellikle temettü ödeyen şirketler için bir değerleme modeli oluşturmak.
-   [ ] **Model Optimizasyonu ve Geriye Dönük Test (Backtesting):**
    -   [ ] **Parametre Optimizasyon Çerçevesi:** Model parametrelerinin (pencere boyutları, eşik değerler vb.) her varlık tipi ve zaman aralığı için otomatik olarak optimize edileceği bir yapı kurmak.
    -   [ ] **Gelişmiş Backtesting Modülü:** Mevcut `simulator.py`'yi, stratejilerin geçmiş performansını, kâr/zarar oranını, maksimum düşüşü (drawdown) ve diğer önemli metrikleri ölçecek şekilde geliştirmek.
-   [ ] **Makine Öğrenmesi Modelinin Geliştirilmesi:**
    -   [ ] **Hisse Senedi Özellikleri:** Mevcut `MachineLearningModel`'i, `FinancialRatioModel`'den gelen oranlar gibi hisse senedine özgü yeni özelliklerle besleyerek daha doğru tahminler yapmasını sağlamak.
-   [ ] **Risk ve Portföy Yönetimi:**
    -   [ ] **Portföy Optimizasyonu:** Kullanıcının risk profiline göre farklı varlıklardan oluşan optimize edilmiş bir portföy önerecek bir modül eklemek (Modern Portföy Teorisi vb. kullanarak).

## Bilinen Sorunlar ve İyileştirme Notları

*   **Otomatik Kod Düzenleme Zorlukları:** Büyük kod bloklarında veya sık güncellenen dosyalarda `replace` komutunun `old_string` eşleşmeme sorunları yaşanmaktadır. Bu durum, manuel müdahale veya daha küçük, atomik değişiklikler gerektirebilir. Gelecekte bu tür otomatik düzenlemeler için daha sağlam yöntemler araştırılmalıdır.