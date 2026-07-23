import SwiftUI
import StoreKit

struct PremiumUpgradeView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var session: UserSession
    @EnvironmentObject private var store: StoreKitManager
    @State private var selectedProductID = StoreKitManager.yearlyProductID
    @State private var isPurchasing = false

    let features = [
        PremiumFeature(title: "V2 ICT Analiz Motoru", description: "FVG, Market Structure ve Killzone verileriyle profesyonel analiz.", icon: "cpu.fill"),
        PremiumFeature(title: "Yüksek Doğruluklu ML Modeli", description: "%64+ doğruluk oranına sahip özel eğitilmiş model.", icon: "brain.head.profile.fill"),
        PremiumFeature(title: "Sınırsız Portföy Takibi", description: "Dilediğiniz kadar sembolü gerçek zamanlı takip edin.", icon: "infinity"),
        PremiumFeature(title: "Reklamsız Deneyim", description: "Uygulama genelinde kesintisiz ve temiz arayüz.", icon: "eye.slash.fill"),
        PremiumFeature(title: "Anlık Bildirimler", description: "Sinyal değişimlerinde anında haberdar olun.", icon: "bell.badge.fill")
    ]

    var body: some View {
        NavigationView {
            ZStack {
                Color.black.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 24) {
                        VStack(spacing: 8) {
                            Text("OptiTrade Pro")
                                .font(.system(size: 32, weight: .bold))
                                .foregroundColor(.white)

                            Text("Yatırımlarınızda Profesyonel Bir Adım Atın")
                                .font(.subheadline)
                                .foregroundColor(.gray)
                        }
                        .padding(.top, 20)

                        if let error = store.errorMessage {
                            Text(error)
                                .font(.caption)
                                .foregroundColor(.red)
                                .multilineTextAlignment(.center)
                                .padding(.horizontal)
                        }

                        HStack(spacing: 16) {
                            ForEach(store.products, id: \.id) { product in
                                let isYearly = product.id == StoreKitManager.yearlyProductID
                                PricingCard(
                                    title: isYearly ? "Yıllık" : "Aylık",
                                    price: product.displayPrice,
                                    period: isYearly ? "yıl" : "ay",
                                    isSelected: selectedProductID == product.id,
                                    discount: isYearly ? "%33 Tasarruf" : nil
                                )
                                .onTapGesture {
                                    selectedProductID = product.id
                                }
                            }
                        }
                        .padding(.horizontal)

                        if store.products.isEmpty && !store.isLoading {
                            VStack(spacing: 8) {
                                PricingCard(title: "Aylık", price: "₺149.99", period: "ay", isSelected: selectedProductID == StoreKitManager.monthlyProductID)
                                    .onTapGesture { selectedProductID = StoreKitManager.monthlyProductID }
                                PricingCard(title: "Yıllık", price: "₺1199.99", period: "yıl", isSelected: selectedProductID == StoreKitManager.yearlyProductID, discount: "%33 Tasarruf")
                                    .onTapGesture { selectedProductID = StoreKitManager.yearlyProductID }
                            }
                            .padding(.horizontal)
                        }

                        VStack(alignment: .leading, spacing: 16) {
                            ForEach(features) { feature in
                                FeatureRow(feature: feature)
                            }
                        }
                        .padding()
                        .background(Color.white.opacity(0.05))
                        .cornerRadius(16)
                        .padding(.horizontal)

                        Button(action: purchase) {
                            HStack {
                                if isPurchasing {
                                    ProgressView().tint(.black)
                                } else {
                                    Text("Premium'a Geç")
                                        .font(.headline)
                                }
                            }
                            .foregroundColor(.black)
                            .frame(maxWidth: .infinity)
                            .frame(height: 56)
                            .background(Color.accentColor)
                            .cornerRadius(28)
                        }
                        .disabled(isPurchasing)
                        .padding(.horizontal)
                        .padding(.top, 12)

                        Button("Geri Yükle") {
                            Task { await store.restorePurchases() }
                        }
                        .font(.footnote)
                        .foregroundColor(.gray)
                        .padding(.top, 4)

                        Text("Ödeme Apple ID hesabınızdan tahsil edilecektir. İstediğiniz zaman iptal edebilirsiniz.")
                            .font(.caption2)
                            .foregroundColor(.gray)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal, 40)
                    }
                    .padding(.bottom, 40)
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Kapat") { dismiss() }
                        .foregroundColor(.gray)
                }
            }
        }
        .task {
            await store.loadProducts()
        }
    }

    private func purchase() {
        guard let product = store.products.first(where: { $0.id == selectedProductID }) else {
            store.errorMessage = "Ürün bilgisi alınamadı. Lütfen tekrar deneyin."
            return
        }
        isPurchasing = true
        Task {
            await store.purchase(product)
            isPurchasing = false
            if store.purchasedProductIDs.contains(product.id) {
                dismiss()
            }
        }
    }
}

struct PremiumFeature: Identifiable {
    let id = UUID()
    let title: String
    let description: String
    let icon: String
}

struct FeatureRow: View {
    let feature: PremiumFeature

    var body: some View {
        HStack(alignment: .top, spacing: 16) {
            Image(systemName: feature.icon)
                .font(.system(size: 24))
                .foregroundColor(.accentColor)
                .frame(width: 32)

            VStack(alignment: .leading, spacing: 4) {
                Text(feature.title)
                    .font(.headline)
                    .foregroundColor(.white)
                Text(feature.description)
                    .font(.subheadline)
                    .foregroundColor(.gray)
            }
        }
    }
}

struct PricingCard: View {
    let title: String
    let price: String
    let period: String
    let isSelected: Bool
    var discount: String? = nil

    var body: some View {
        VStack(spacing: 12) {
            if let disc = discount {
                Text(disc)
                    .font(.system(size: 10, weight: .bold))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(Color.accentColor)
                    .foregroundColor(.black)
                    .cornerRadius(4)
            } else {
                Spacer().frame(height: 20)
            }

            Text(title)
                .font(.headline)
                .foregroundColor(.gray)

            VStack(spacing: 2) {
                Text(price)
                    .font(.title2)
                    .fontWeight(.bold)
                    .foregroundColor(.white)
                Text("/\(period)")
                    .font(.caption)
                    .foregroundColor(.gray)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 16)
        .background(isSelected ? Color.accentColor.opacity(0.1) : Color.white.opacity(0.05))
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(isSelected ? Color.accentColor : Color.clear, lineWidth: 2)
        )
    }
}
