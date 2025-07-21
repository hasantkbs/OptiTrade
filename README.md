# OptiTrade

OptiTrade, yapay zeka destekli bir ticaret sinyali üretim ve analiz platformudur. Çeşitli finansal modelleri kullanarak piyasa verilerini analiz eder, ticaret sinyalleri üretir ve bu sinyalleri bir puanlama motoru aracılığıyla değerlendirir. Platform, geriye dönük test (backtesting) yetenekleri ile stratejilerin performansını simüle etme imkanı sunar.

## Özellikler

- **Çeşitli Finansal Modeller:** Fiyat trendi, haber duyarlılığı, piyasa koşulları sınıflandırması, sosyal duyarlılık, hacim artışı ve destek/direnç seviyeleri gibi çeşitli yapay zeka modelleri.
- **Ticaret Sinyali Puanlama Motoru:** Üretilen sinyalleri kapsamlı bir şekilde değerlendirir ve puanlar.
- **Geriye Dönük Test (Backtesting) Simülatörü:** Geliştirilen ticaret stratejilerinin geçmiş veriler üzerindeki performansını simüle eder.
- **Veri Çekme ve İşleme:** Finansal verileri otomatik olarak çeker ve işler.

## Kurulum

OptiTrade projesini yerel makinenizde kurmak ve çalıştırmak için aşağıdaki adımları izleyin:

### Önkoşullar

- Python 3.8+
- Conda (Anaconda veya Miniconda)

### Adımlar

1.  **Depoyu Klonlayın:**
    ```bash
    git clone https://github.com/your-username/OptiTrade.git
    cd OptiTrade
    ```
    *(`your-username` kısmını kendi GitHub kullanıcı adınızla değiştirin.)*

2.  **Conda Ortamını Oluşturun ve Etkinleştirin:**
    Proje için gerekli tüm bağımlılıkları içeren bir Conda ortamı oluşturmak için `environment.yml` dosyasını kullanın:
    ```bash
    conda env create -f environment.yml
    conda activate optitrade
    ```

3.  **Gerekli Python Paketlerini Yükleyin:**
    `requirements.txt` dosyasında belirtilen ek paketleri yükleyin:
    ```bash
    pip install -r requirements.txt
    ```

## Kullanım

Conda ortamını etkinleştirdikten sonra (yukarıdaki kurulum adımlarına bakın), projenin ana işlevlerini çalıştırmak için aşağıdaki betikleri kullanabilirsiniz:

### Veri Çekme

Finansal verileri çekmek için `fetch_data.py` betiğini kullanın. Örneğin, BTC-USD verilerini çekmek için:

```bash
python scripts/fetch_data.py --symbol BTC-USD
```

### Ana Uygulamayı Çalıştırma

OptiTrade'in ana uygulamasını çalıştırmak için `main.py` betiğini kullanın. Bu betik, tüm modelleri entegre eder ve ticaret sinyalleri üretir:

```bash
python -m src.optitrade.main --symbol BTC-USD
```

### Puanlama Motorunu Çalıştırma

Üretilen ticaret sinyallerini puanlamak için `run_scoring_engine.py` betiğini kullanın:

```bash
python scripts/run_scoring_engine.py --symbol BTC-USD
```

## Proje Yapısı

Projenin ana dizin yapısı aşağıdaki gibidir:

```
OptiTrade/
├── data/                 # Ham, işlenmiş ve harici veri dosyaları
├── notebooks/            # Jupyter not defterleri (veri keşfi, model geliştirme)
├── scripts/              # Yardımcı betikler (veri çekme, puanlama motoru çalıştırma)
└── src/                  # Ana kaynak kodu
    └── optitrade/        # OptiTrade paketi
        ├── alerting/     # Uyarı sistemleri
        ├── backtesting/  # Geriye dönük test simülatörü
        ├── data/         # Veri yükleme ve işleme modülleri
        ├── models/       # Yapay zeka modelleri
        ├── scoring/      # Sinyal puanlama motoru
        └── utils/        # Yardımcı fonksiyonlar ve sınıflar
```
