import SwiftUI
import FirebaseCore

@main
struct OptiTradeApp: App {
    @StateObject private var session     = UserSession.shared
    @StateObject private var firebase    = FirebaseService.shared
    @StateObject private var preferences = UserPreferences()
    @StateObject private var storeKit    = StoreKitManager.shared

    init() {
        FirebaseApp.configure()
        let savedURL = UserDefaults.standard.string(forKey: "api_base_url") ?? "https://api.optitrade.app"
        APIService.shared.baseURL = savedURL
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(session)
                .environmentObject(firebase)
                .environmentObject(preferences)
                .environmentObject(storeKit)
        }
    }
}

struct RootView: View {
    @EnvironmentObject var preferences: UserPreferences
    @EnvironmentObject var session:     UserSession
    @EnvironmentObject var firebase:    FirebaseService

    var body: some View {
        Group {
            if !preferences.hasCompletedOnboarding {
                MarketSelectionView(isOnboarding: true) {
                }
            } else {
                ContentView()
            }
        }
        .onAppear {
            Task { await preferences.fetchFromFirebase() }
        }
    }
}
