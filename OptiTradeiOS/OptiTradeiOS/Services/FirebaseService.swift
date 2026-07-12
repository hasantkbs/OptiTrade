import Foundation
import FirebaseAuth
import FirebaseFirestore

// ─────────────────────────────────────────────────────────────────────────────
// MARK: - Firebase User Model
// ─────────────────────────────────────────────────────────────────────────────
struct FirebaseUserProfile: Codable {
    let uid: String
    var displayName: String
    var email: String
    var defaultAssetType: String
    var showNeutralInScan: Bool
    var isPremium: Bool
    var isAdmin: Bool
    var subscriptionLevel: String
    var focusAssets: [String]
    var appTheme: String
    var createdAt: Date

    static func from(user: User) -> FirebaseUserProfile {
        FirebaseUserProfile(
            uid: user.uid,
            displayName: user.displayName ?? "",
            email: user.email ?? "",
            defaultAssetType: "stock",
            showNeutralInScan: true,
            isPremium: false,
            isAdmin: false,
            subscriptionLevel: "FREE",
            focusAssets: [],
            appTheme: "dark",
            createdAt: Date()
        )
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// MARK: - FirebaseService
// ─────────────────────────────────────────────────────────────────────────────

@MainActor
final class FirebaseService: ObservableObject {
    static let shared = FirebaseService()

    @Published var currentUser: User?
    @Published var isLoading = false
    @Published var authError: String?

    private let db = Firestore.firestore()
    private var authListener: AuthStateDidChangeListenerHandle?

    private init() {
        authListener = Auth.auth().addStateDidChangeListener { [weak self] _, user in
            Task { @MainActor in
                self?.currentUser = user
            }
        }
    }

    deinit {
        if let handle = authListener {
            Auth.auth().removeStateDidChangeListener(handle)
        }
    }

    var isAuthenticated: Bool { currentUser != nil }

    // ── Auth ──────────────────────────────────────────────────────────────────

    func signIn(email: String, password: String) async throws {
        isLoading = true
        authError = nil
        defer { isLoading = false }
        let result = try await Auth.auth().signIn(withEmail: email, password: password)
        currentUser = result.user
    }

    func signInWithApple(credential: AuthCredential) async throws {
        isLoading = true
        authError = nil
        defer { isLoading = false }
        let result = try await Auth.auth().signIn(with: credential)
        currentUser = result.user

        // If new user, create profile
        if (try? await fetchUserProfile()) != nil {
            // User exists, update if needed
        } else {
            let newProfile = FirebaseUserProfile.from(user: result.user)
            try await saveUserProfile(newProfile)
        }
    }

    func signUp(email: String, password: String, displayName: String) async throws {
        isLoading = true
        authError = nil
        defer { isLoading = false }

        let result = try await Auth.auth().createUser(withEmail: email, password: password)
        let changeRequest = result.user.createProfileChangeRequest()
        changeRequest.displayName = displayName
        try await changeRequest.commitChanges()
        currentUser = result.user

        // Create Firestore user document
        let profile = FirebaseUserProfile.from(user: result.user)
        try await saveUserProfile(profile)
    }

    func signOut() throws {
        try Auth.auth().signOut()
        currentUser = nil
    }

    func sendPasswordReset(email: String) async throws {
        try await Auth.auth().sendPasswordReset(withEmail: email)
    }

    // ── ID Token for API Requests ──────────────────────────────────────────────

    func getIDToken() async -> String? {
        guard let user = currentUser else { return nil }
        return try? await user.getIDToken()
    }

    // ── Firestore: User Profile ────────────────────────────────────────────────

    private func userDoc() -> DocumentReference? {
        guard let uid = currentUser?.uid else { return nil }
        return db.collection("users").document(uid)
    }

    func saveUserProfile(_ profile: FirebaseUserProfile) async throws {
        guard let ref = userDoc() else { return }
        let data: [String: Any] = [
            "uid": profile.uid,
            "displayName": profile.displayName,
            "email": profile.email,
            "defaultAssetType": profile.defaultAssetType,
            "showNeutralInScan": profile.showNeutralInScan,
            "isPremium": profile.isPremium,
            "isAdmin": profile.isAdmin,
            "subscriptionLevel": profile.subscriptionLevel,
            "focusAssets": profile.focusAssets,
            "appTheme": profile.appTheme,
            "createdAt": Timestamp(date: profile.createdAt),
        ]
        try await ref.setData(data, merge: true)
    }

    func fetchUserProfile() async throws -> FirebaseUserProfile? {
        guard let ref = userDoc() else { return nil }
        let doc = try await ref.getDocument()
        guard let d = doc.data() else { return nil }
        return FirebaseUserProfile(
            uid: d["uid"] as? String ?? "",
            displayName: d["displayName"] as? String ?? "",
            email: d["email"] as? String ?? "",
            defaultAssetType: d["defaultAssetType"] as? String ?? "stock",
            showNeutralInScan: d["showNeutralInScan"] as? Bool ?? true,
            isPremium: d["isPremium"] as? Bool ?? false,
            isAdmin: d["isAdmin"] as? Bool ?? false,
            subscriptionLevel: d["subscriptionLevel"] as? String ?? "FREE",
            focusAssets: d["focusAssets"] as? [String] ?? [],
            appTheme: d["appTheme"] as? String ?? "dark",
            createdAt: (d["createdAt"] as? Timestamp)?.dateValue() ?? Date()
        )
    }

    // ── Firestore: Watchlist ───────────────────────────────────────────────────

    func fetchWatchlist() async throws -> [WatchlistItemData] {
        guard let ref = userDoc() else { return [] }
        let snap = try await ref.collection("watchlist").getDocuments()
        return snap.documents.compactMap { doc -> WatchlistItemData? in
            let d = doc.data()
            guard let symbol = d["symbol"] as? String,
                  let assetType = d["assetType"] as? String else { return nil }
            return WatchlistItemData(
                id: UUID(uuidString: doc.documentID) ?? UUID(),
                symbol: symbol,
                potentialPrice: d["potentialPrice"] as? Double,
                assetType: assetType
            )
        }
    }

    func saveWatchlist(_ items: [WatchlistItemData]) async throws {
        guard let ref = userDoc() else { return }
        let colRef = ref.collection("watchlist")

        // Delete existing
        let existing = try await colRef.getDocuments()
        for doc in existing.documents { try await doc.reference.delete() }

        // Write new
        for item in items {
            var data: [String: Any] = ["symbol": item.symbol, "assetType": item.assetType]
            if let pp = item.potentialPrice { data["potentialPrice"] = pp }
            try await colRef.document(item.id.uuidString).setData(data)
        }
    }

    // ── Firestore: Paper Trades ────────────────────────────────────────────────

    func fetchPaperTrades() async throws -> [PaperTrade] {
        guard let ref = userDoc() else { return [] }
        let snap = try await ref.collection("paperTrades").getDocuments()
        return snap.documents.compactMap { doc -> PaperTrade? in
            let d = doc.data()
            guard
                let symbol = d["symbol"] as? String,
                let assetType = d["assetType"] as? String,
                let dirRaw = d["direction"] as? String,
                let direction = PaperTrade.TradeDirection(rawValue: dirRaw),
                let entryPrice = d["entryPrice"] as? Double,
                let quantity = d["quantity"] as? Double,
                let entryTS = d["entryDate"] as? Timestamp,
                let isOpen = d["isOpen"] as? Bool,
                let score = d["analysisScore"] as? Int,
                let code = d["decisionCode"] as? String
            else { return nil }

            return PaperTrade(
                id: UUID(uuidString: doc.documentID) ?? UUID(),
                symbol: symbol,
                assetType: assetType,
                direction: direction,
                entryPrice: entryPrice,
                quantity: quantity,
                entryDate: entryTS.dateValue(),
                exitPrice: d["exitPrice"] as? Double,
                exitDate: (d["exitDate"] as? Timestamp)?.dateValue(),
                isOpen: isOpen,
                analysisScore: score,
                decisionCode: code
            )
        }
    }

    func savePaperTrades(_ trades: [PaperTrade]) async throws {
        guard let ref = userDoc() else { return }
        let colRef = ref.collection("paperTrades")

        let existing = try await colRef.getDocuments()
        for doc in existing.documents { try await doc.reference.delete() }

        for trade in trades {
            var data: [String: Any] = [
                "symbol": trade.symbol,
                "assetType": trade.assetType,
                "direction": trade.direction.rawValue,
                "entryPrice": trade.entryPrice,
                "quantity": trade.quantity,
                "entryDate": Timestamp(date: trade.entryDate),
                "isOpen": trade.isOpen,
                "analysisScore": trade.analysisScore,
                "decisionCode": trade.decisionCode,
            ]
            if let ep = trade.exitPrice { data["exitPrice"] = ep }
            if let ed = trade.exitDate { data["exitDate"] = Timestamp(date: ed) }
            try await colRef.document(trade.id.uuidString).setData(data)
        }
    }

    // ── Firestore: Portfolio Holdings ──────────────────────────────────────────

    func fetchPortfolioHoldings() async throws -> [PortfolioHolding] {
        guard let ref = userDoc() else { return [] }
        let snap = try await ref.collection("portfolioHoldings").getDocuments()
        return snap.documents.compactMap { doc -> PortfolioHolding? in
            let d = doc.data()
            guard
                let symbol = d["symbol"] as? String,
                let assetType = d["assetType"] as? String,
                let quantity = d["quantity"] as? Double,
                let purchasePrice = d["purchasePrice"] as? Double,
                let purchaseTS = d["purchaseDate"] as? Timestamp
            else { return nil }

            return PortfolioHolding(
                id: UUID(uuidString: doc.documentID) ?? UUID(),
                symbol: symbol,
                assetType: assetType,
                quantity: quantity,
                purchasePrice: purchasePrice,
                purchaseDate: purchaseTS.dateValue()
            )
        }
    }

    func savePortfolioHoldings(_ holdings: [PortfolioHolding]) async throws {
        guard let ref = userDoc() else { return }
        let colRef = ref.collection("portfolioHoldings")

        let existing = try await colRef.getDocuments()
        for doc in existing.documents { try await doc.reference.delete() }

        for holding in holdings {
            let data: [String: Any] = [
                "symbol": holding.symbol,
                "assetType": holding.assetType,
                "quantity": holding.quantity,
                "purchasePrice": holding.purchasePrice,
                "purchaseDate": Timestamp(date: holding.purchaseDate),
            ]
            try await colRef.document(holding.id.uuidString).setData(data)
        }
    }

    // ── Firestore: Search History ──────────────────────────────────────────────

    func fetchSearchHistory() async throws -> [SearchHistoryItem] {
        guard let ref = userDoc() else { return [] }
        let snap = try await ref.collection("searchHistory")
            .order(by: "date", descending: true)
            .limit(to: 20)
            .getDocuments()
        return snap.documents.compactMap { doc -> SearchHistoryItem? in
            let d = doc.data()
            guard
                let symbol = d["symbol"] as? String,
                let assetType = d["assetType"] as? String,
                let ts = d["date"] as? Timestamp,
                let score = d["score"] as? Int,
                let code = d["decisionCode"] as? String
            else { return nil }
            return SearchHistoryItem(
                id: UUID(uuidString: doc.documentID) ?? UUID(),
                symbol: symbol,
                assetType: assetType,
                date: ts.dateValue(),
                score: score,
                decisionCode: code
            )
        }
    }

    func addSearchHistory(_ item: SearchHistoryItem) async throws {
        guard let ref = userDoc() else { return }
        let data: [String: Any] = [
            "symbol": item.symbol,
            "assetType": item.assetType,
            "date": Timestamp(date: item.date),
            "score": item.score,
            "decisionCode": item.decisionCode,
        ]
        try await ref.collection("searchHistory").document(item.id.uuidString).setData(data)
    }
}
