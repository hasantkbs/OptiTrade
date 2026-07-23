import StoreKit

@MainActor
final class StoreKitManager: ObservableObject {
    static let shared = StoreKitManager()

    @Published private(set) var products: [Product] = []
    @Published private(set) var purchasedProductIDs = Set<String>()
    @Published private(set) var isLoading = false
    @Published var errorMessage: String?

    static let monthlyProductID = "com.algorix.optitrade.premium.monthly"
    static let yearlyProductID  = "com.algorix.optitrade.premium.yearly"

    private var updates: Task<Void, Never>?

    private init() {
        updates = observeTransactionUpdates()
    }

    deinit {
        updates?.cancel()
    }

    func loadProducts() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            products = try await Product.products(for: [
                Self.monthlyProductID,
                Self.yearlyProductID,
            ]).sorted { $0.price < $1.price }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func purchase(_ product: Product) async {
        errorMessage = nil
        do {
            let result = try await product.purchase()
            switch result {
            case .success(let verification):
                if case .verified(let transaction) = verification {
                    purchasedProductIDs.insert(transaction.productID)
                    await transaction.finish()
                    await updatePremiumStatus()
                }
            case .pending:
                break
            case .userCancelled:
                break
            @unknown default:
                break
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func restorePurchases() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            try await AppStore.sync()
            await updatePurchasedProducts()
            await updatePremiumStatus()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func updatePurchasedProducts() async {
        var purchased = Set<String>()
        for await result in Transaction.currentEntitlements {
            if case .verified(let transaction) = result {
                purchased.insert(transaction.productID)
            }
        }
        purchasedProductIDs = purchased
    }

    private func updatePremiumStatus() async {
        let hasPremium = !purchasedProductIDs.isEmpty
        UserSession.shared.isPremium = hasPremium
        UserSession.shared.subscriptionLevel = hasPremium ? .premium : .free
        if hasPremium, let profile = try? await FirebaseService.shared.fetchUserProfile() {
            var updated = profile
            updated.isPremium = true
            updated.subscriptionLevel = "PREMIUM"
            try? await FirebaseService.shared.saveUserProfile(updated)
        }
    }

    private func observeTransactionUpdates() -> Task<Void, Never> {
        Task(priority: .background) { [weak self] in
            for await result in Transaction.updates {
                guard let self else { break }
                if case .verified(let transaction) = result {
                    await MainActor.run {
                        self.purchasedProductIDs.insert(transaction.productID)
                    }
                    await transaction.finish()
                    await MainActor.run {
                        Task { await self.updatePremiumStatus() }
                    }
                }
            }
        }
    }
}
