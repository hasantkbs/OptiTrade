import SwiftUI
import FirebaseCore

@main
struct OptiTradeApp: App {
    @StateObject private var session     = UserSession.shared
    @StateObject private var firebase    = FirebaseService.shared
    @StateObject private var preferences = UserPreferences()

    init() {
        FirebaseApp.configure()
        let savedURL = UserDefaults.standard.string(forKey: "api_base_url") ?? "http://localhost:8000"
        APIService.shared.baseURL = savedURL

        // Google Ads Başlatma (SDK eklendiğinde açılacak)
        // GADMobileAds.sharedInstance().start(completionHandler: nil)
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(session)
                .environmentObject(firebase)
                .environmentObject(preferences)
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// MARK: - RootView — Onboarding akışı burada yönetilir
// ─────────────────────────────────────────────────────────────────────────────

struct RootView: View {
    @EnvironmentObject var preferences: UserPreferences
    @EnvironmentObject var session:     UserSession
    @EnvironmentObject var firebase:    FirebaseService

    var body: some View {
        Group {
            if !preferences.hasCompletedOnboarding {
                // İlk açılışta piyasa seçimi
                MarketSelectionView(isOnboarding: true) {
                    // Onboarding tamamlandı → ana ekrana geç
                }
            } else {
                ContentView()
            }
        }
        .onAppear {
            // Giriş yapılmışsa Firebase'den tercihi çek
            Task { await preferences.fetchFromFirebase() }
        }
    }
}
