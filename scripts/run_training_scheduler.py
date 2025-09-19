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

def train_all_models(retries: int = 3, delay: int = 600):
    """
    Tüm zaman aralıkları için model eğitimini tetikler.
    Başarısız olursa yeniden dener.
    """
    intervals = ["1d", "4h", "15m"]
    python_executable = sys.executable
    train_script_path = os.path.join(project_root, "scripts", "train_model.py")

    logging.info("Otomatik model eğitim görevi başlatıldı.")
    
    for interval in intervals:
        for i in range(retries):
            try:
                logging.info(f"'{interval}' aralığı için eğitim süreci başlatılıyor (Deneme {i+1}/{retries})...")
                command = [python_executable, train_script_path, "--interval", interval]
                
                result = subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True
                )
                
                logging.info(f"'{interval}' aralığı için eğitim script'i çıktısı:\n{result.stdout}")
                if result.stderr:
                    logging.warning(f"'{interval}' aralığı için eğitim script'i stderr çıktısı:\n{result.stderr}")

                logging.info(f"'{interval}' aralığı için eğitim başarıyla tamamlandı.")
                break  # Başarılı olursa döngüden çık
            except subprocess.CalledProcessError as e:
                logging.error(f"'{interval}' aralığı için eğitim sırasında bir hata oluştu (Deneme {i+1}/{retries}). Return code: {e.returncode}")
                logging.error(f"Hata Çıktısı:\n{e.stderr}")
                if i < retries - 1:
                    logging.info(f"{delay} saniye sonra yeniden denenecek...")
                    time.sleep(delay)
                else:
                    logging.error(f"'{interval}' için tüm yeniden denemeler başarısız oldu.")
            except Exception as e:
                logging.error(f"Beklenmedik bir hata oluştu: {e}")
                break # Beklenmedik hatalarda yeniden deneme yapma

    logging.info("Tüm modellerin eğitimi tamamlandı.")

# Görevi zamanla
# Her Pazar sabaha karşı 02:00'de çalışacak şekilde ayarla
schedule.every().sunday.at("02:00").do(train_all_models)

logging.info("Model eğitim zamanlayıcısı başlatıldı. Görev her Pazar 02:00'de çalışacak.")

# Zamanlayıcıyı sürekli çalıştır
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Otomatik model eğitim zamanlayıcısı.')
    parser.add_argument('--day', type=str, default='sunday', help='Eğitimin çalışacağı gün (örn: monday, tuesday, ..., sunday).')
    parser.add_argument('--time', type=str, default='02:00', help='Eğitimin çalışacağı saat (24-saat formatı, HH:MM).')
    parser.add_argument('--run_once', action='store_true', help='Zamanlayıcıyı başlatmadan görevi bir kere çalıştırır.')

    args = parser.parse_args()

    if args.run_once:
        logging.info("'--run_once' argümanı belirtildi. Görev bir kere çalıştırılacak.")
        train_all_models()
    else:
        logging.info(f"Model eğitim zamanlayıcısı başlatıldı. Görev her {args.day} saat {args.time}'de çalışacak.")
        
        # Görevi zamanla
        schedule_job = getattr(schedule.every(), args.day.lower())
        schedule_job.at(args.time).do(train_all_models)

        # Zamanlayıcıyı sürekli çalıştır
        while True:
            schedule.run_pending()
            time.sleep(60) # Her 60 saniyede bir kontrol et
