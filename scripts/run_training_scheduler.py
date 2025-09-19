import schedule
import time
import subprocess
import logging
import sys
import os

# Loglama yapılandırması
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Proje kök dizinini al
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def train_all_models():
    """
    Tüm zaman aralıkları için model eğitimini tetikler.
    """
    intervals = ["1d", "4h", "15m"]
    python_executable = sys.executable  # Mevcut Conda ortamının Python'u
    train_script_path = os.path.join(project_root, "scripts", "train_model.py")

    logging.info("Otomatik model eğitim görevi başlatıldı.")
    
    for interval in intervals:
        try:
            logging.info(f"'{interval}' aralığı için eğitim süreci başlatılıyor...")
            command = [python_executable, train_script_path, "--interval", interval]
            
            # subprocess.run kullanarak komutu çalıştır ve çıktıyı yakala
            result = subprocess.run(
                command,
                check=True,         # Komut hata ile sonuçlanırsa exception fırlat
                capture_output=True, # stdout ve stderr'i yakala
                text=True           # Çıktıyı metin olarak işle
            )
            
            # Eğitim script'inin çıktısını logla
            logging.info(f"'{interval}' aralığı için eğitim script'i çıktısı:\n{result.stdout}")
            if result.stderr:
                logging.warning(f"'{interval}' aralığı için eğitim script'i stderr çıktısı:\n{result.stderr}")

            logging.info(f"'{interval}' aralığı için eğitim başarıyla tamamlandı.")
        except subprocess.CalledProcessError as e:
            logging.error(f"'{interval}' aralığı için eğitim sırasında bir hata oluştu. Return code: {e.returncode}")
            logging.error(f"Hata Çıktısı:\n{e.stderr}")
        except Exception as e:
            logging.error(f"Beklenmedik bir hata oluştu: {e}")

    logging.info("Tüm modellerin eğitimi tamamlandı.")

# Görevi zamanla
# Her Pazar sabaha karşı 02:00'de çalışacak şekilde ayarla
schedule.every().sunday.at("02:00").do(train_all_models)

logging.info("Model eğitim zamanlayıcısı başlatıldı. Görev her Pazar 02:00'de çalışacak.")

# Zamanlayıcıyı sürekli çalıştır
if __name__ == "__main__":
    # Başlangıçta bir kere hemen çalıştır (isteğe bağlı)
    # train_all_models()

    while True:
        schedule.run_pending()
        time.sleep(60) # Her 60 saniyede bir kontrol et
