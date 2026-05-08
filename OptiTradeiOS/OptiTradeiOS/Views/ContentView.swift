import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var session: UserSession
    @EnvironmentObject private var firebase: FirebaseService

    var body: some View {
        Group {
            if firebase.isAuthenticated || session.isGuestMode {
                if !session.onboardingDone {
                    OnboardingView()
                } else {
                    mainTabs
                }
            } else {
                AuthView()
            }
        }
        .animation(.easeInOut(duration: 0.35), value: firebase.isAuthenticated)
        .animation(.easeInOut(duration: 0.35), value: session.onboardingDone)
        .preferredColorScheme(colorScheme)
        .task(id: firebase.isAuthenticated) {
            if firebase.isAuthenticated {
                // Update session display name from Firebase user
                if let fbUser = firebase.currentUser {
                    session.displayName = fbUser.displayName ?? session.displayName
                    session.userEmail   = fbUser.email ?? session.userEmail
                }
                // Sync cloud data to local
                await session.syncFromFirebase()
            }
        }
    }

    private var mainTabs: some View {
        TabView {
            DashboardView()
                .tabItem { Label("Tarama", systemImage: "chart.bar.fill") }

            SearchView()
                .tabItem { Label("Analiz", systemImage: "magnifyingglass") }

            PaperTradeView()
                .tabItem { Label("Beta Trade", systemImage: "chart.line.uptrend.xyaxis") }

            PortfolioAnalysisView()
                .tabItem { Label("Portfoy", systemImage: "chart.pie.fill") }

            WatchlistView()
                .tabItem { Label("Takip", systemImage: "star.fill") }

            SettingsView()
                .tabItem { Label("Ayarlar", systemImage: "gearshape.fill") }
        }
    }

    private var colorScheme: ColorScheme? {
        switch session.appTheme {
        case .dark:   return .dark
        case .light:  return .light
        case .system: return nil
        }
    }
}
