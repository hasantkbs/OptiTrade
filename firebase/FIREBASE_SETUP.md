# Firebase Kurulum & Deploy Kılavuzu — OptiTrade

## 1. Firebase CLI Kurulumu

```bash
npm install -g firebase-tools
firebase login
firebase use optitrade-fcda9
```

---

## 2. Firestore Rules Deploy

```bash
firebase deploy --only firestore:rules
firebase deploy --only firestore:indexes
```

### Kural Özeti

| Koleksiyon | Okuma | Yazma | Silme |
|---|---|---|---|
| `/users/{uid}` | Sadece kendi UID'si | Sadece kendi UID'si (alan kısıtlı) | Yasak |
| `/users/{uid}/watchlist/{id}` | Sahibi | Sahibi (symbol+assetType zorunlu) | Sahibi |
| `/users/{uid}/paperTrades/{id}` | Sahibi | Sahibi (oluşturma tam, güncelleme sadece exit alanları) | Sahibi |
| `/users/{uid}/searchHistory/{id}` | Sahibi | Sahibi (oluşturma), güncelleme yasak | Sahibi |
| Diğer tüm yollar | **YASAK** | **YASAK** | **YASAK** |

---

## 3. Authentication Ayarları (Firebase Console)

1. **Console → Authentication → Sign-in method**
   - `Email/Password` → **Etkinleştir**
   - `Email link (passwordless)` → Kapalı bırakın

2. **Console → Authentication → Settings → Authorized domains**
   ```
   localhost
   optitrade-fcda9.web.app
   optitrade-fcda9.firebaseapp.com
   ```

3. **Console → Authentication → Templates**
   - Gönderici adı: `OptiTrade`
   - Şifre sıfırlama ve doğrulama şablonlarını Türkçe'ye çevirin
     (içerik `firebase/auth-config.yaml` dosyasında referans olarak verilmiştir)

---

## 4. Backend — Firebase Admin SDK

```bash
cd backend
pip install firebase-admin==6.5.0
```

Firebase Console → Proje Ayarları → Hizmet Hesapları → **Yeni özel anahtar oluştur**
JSON dosyasını `backend/firebase-credentials.json` olarak kaydedin.

`.env` dosyasına ekleyin:
```
FIREBASE_CREDENTIALS_PATH=firebase-credentials.json
```

> `firebase-credentials.json` dosyasını asla Git'e commit etmeyin.
> `.gitignore`'a eklenmiş olduğundan emin olun.

---

## 5. Emülatör ile Yerel Test

```bash
firebase emulators:start
```

Emülatör adresleri:
| Servis | URL |
|---|---|
| Auth | http://localhost:9099 |
| Firestore | http://localhost:8080 |
| Emülatör UI | http://localhost:4000 |

iOS uygulamasında test için `FirebaseService.swift` başına ekleyin:
```swift
// Sadece geliştirme ortamında
#if DEBUG
Auth.auth().useEmulator(withHost: "localhost", port: 9099)
let settings = Firestore.firestore().settings
settings.host = "localhost:8080"
settings.isSSLEnabled = false
Firestore.firestore().settings = settings
#endif
```

---

## 6. Firestore Veri Yapısı

```
users/
  {uid}/
    displayName: string
    email: string
    defaultAssetType: "stock" | "crypto"
    showNeutralInScan: bool
    appTheme: "dark" | "light" | "system"
    createdAt: timestamp

    watchlist/
      {uuid}/
        symbol: string          // "THYAO.IS"
        assetType: string       // "stock"
        potentialPrice: number? // opsiyonel

    paperTrades/
      {uuid}/
        symbol: string
        assetType: string
        direction: "LONG" | "SHORT"
        entryPrice: number
        quantity: number
        entryDate: timestamp
        isOpen: bool
        analysisScore: number
        decisionCode: string
        exitPrice: number?      // opsiyonel
        exitDate: timestamp?    // opsiyonel

    searchHistory/
      {uuid}/
        symbol: string
        assetType: string
        date: timestamp
        score: number
        decisionCode: string
```

---

## 7. Güvenlik Kontrol Listesi

- [ ] `firebase-credentials.json` `.gitignore`'da
- [ ] Firestore rules deploy edildi
- [ ] Indexes deploy edildi
- [ ] Auth'da sadece Email/Password aktif
- [ ] Authorized domains güncellendi
- [ ] Backend'de `FIREBASE_CREDENTIALS_PATH` env değişkeni set edildi
- [ ] iOS'ta `GoogleService-Info.plist` proje hedefine eklendi
