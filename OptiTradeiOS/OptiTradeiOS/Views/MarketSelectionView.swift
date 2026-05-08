// OptiTrade — MarketSelectionView
// Onboarding ve Settings'den çağrılır.
// Kullanıcı: TR / US / CRYPTO seçer → tercihi Firebase'e kaydedilir.

import SwiftUI

struct MarketSelectionView: View {

    @EnvironmentObject var preferences: UserPreferences
    var isOnboarding: Bool = false          // true → tam ekran, false → settings sheet
    var onComplete: (() -> Void)? = nil

    @State private var selectedMarket: TradingMarket = .tr
    @State private var isSaving = false
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            Color(hex: "#0A0E1A").ignoresSafeArea()

            VStack(spacing: 0) {
                // ── Başlık ────────────────────────────────────────────────────
                VStack(spacing: 8) {
                    if isOnboarding {
                        Text("OptiTrade'e\nHoş Geldiniz")
                            .font(.system(size: 32, weight: .bold))
                            .foregroundColor(.white)
                            .multilineTextAlignment(.center)
                        Text("Hangi piyasada işlem yapıyorsunuz?")
                            .font(.subheadline)
                            .foregroundColor(.gray)
                    } else {
                        Text("Piyasa Seçimi")
                            .font(.title2.bold())
                            .foregroundColor(.white)
                        Text("Haber filtresi ve arama bu tercihle yapılandırılır")
                            .font(.caption)
                            .foregroundColor(.gray)
                    }
                }
                .padding(.top, isOnboarding ? 60 : 24)
                .padding(.bottom, 40)

                // ── Piyasa Kartları ───────────────────────────────────────────
                VStack(spacing: 16) {
                    ForEach(TradingMarket.allCases, id: \.self) { market in
                        MarketCard(
                            market:     market,
                            isSelected: selectedMarket == market
                        ) {
                            withAnimation(.spring(response: 0.3)) {
                                selectedMarket = market
                            }
                        }
                    }
                }
                .padding(.horizontal, 24)

                // ── Bilgi kutusu (Kripto seçilince) ──────────────────────────
                if selectedMarket == .crypto {
                    HStack(spacing: 8) {
                        Image(systemName: "info.circle")
                            .foregroundColor(.blue)
                        Text("Kripto piyasası 7/24 globaldir. Haber filtresi otomatik uygulanır.")
                            .font(.caption)
                            .foregroundColor(.gray)
                    }
                    .padding(12)
                    .background(Color.blue.opacity(0.08))
                    .cornerRadius(10)
                    .padding(.horizontal, 24)
                    .padding(.top, 12)
                    .transition(.opacity.combined(with: .move(edge: .top)))
                }

                Spacer()

                // ── Devam / Kaydet ────────────────────────────────────────────
                Button {
                    save()
                } label: {
                    if isSaving {
                        ProgressView()
                            .tint(.black)
                            .frame(maxWidth: .infinity)
                            .frame(height: 54)
                    } else {
                        Text(isOnboarding ? "Devam Et" : "Kaydet")
                            .font(.headline)
                            .foregroundColor(.black)
                            .frame(maxWidth: .infinity)
                            .frame(height: 54)
                    }
                }
                .background(
                    LinearGradient(
                        colors: [Color(hex: "#00D4FF"), Color(hex: "#0094FF")],
                        startPoint: .leading, endPoint: .trailing
                    )
                )
                .cornerRadius(14)
                .padding(.horizontal, 24)
                .padding(.bottom, isOnboarding ? 50 : 24)
                .disabled(isSaving)
            }
        }
        .onAppear {
            selectedMarket = preferences.selectedMarket
        }
    }

    private func save() {
        isSaving = true
        if isOnboarding {
            preferences.completeOnboarding(market: selectedMarket)
        } else {
            preferences.setMarket(selectedMarket)
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) {
            isSaving = false
            onComplete?()
            if !isOnboarding { dismiss() }
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// MARK: - MarketCard
// ─────────────────────────────────────────────────────────────────────────────

private struct MarketCard: View {
    let market: TradingMarket
    let isSelected: Bool
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 16) {
                // Flag / Icon
                Text(market.flag)
                    .font(.system(size: 32))
                    .frame(width: 52, height: 52)
                    .background(Color.white.opacity(0.06))
                    .cornerRadius(12)

                // Bilgi
                VStack(alignment: .leading, spacing: 4) {
                    Text(market.displayName)
                        .font(.headline)
                        .foregroundColor(.white)
                    Text(market.description)
                        .font(.caption)
                        .foregroundColor(.gray)
                        .lineLimit(2)

                    // Endeks etiketi
                    HStack(spacing: 4) {
                        Image(systemName: "chart.line.uptrend.xyaxis")
                            .font(.caption2)
                            .foregroundColor(accentColor)
                        Text(market.indexName)
                            .font(.caption2.weight(.medium))
                            .foregroundColor(accentColor)
                    }
                }

                Spacer()

                // Seçim işareti
                ZStack {
                    Circle()
                        .stroke(isSelected ? accentColor : Color.gray.opacity(0.3), lineWidth: 2)
                        .frame(width: 24, height: 24)
                    if isSelected {
                        Circle()
                            .fill(accentColor)
                            .frame(width: 14, height: 14)
                    }
                }
            }
            .padding(16)
            .background(
                RoundedRectangle(cornerRadius: 16)
                    .fill(isSelected ? accentColor.opacity(0.12) : Color.white.opacity(0.05))
                    .overlay(
                        RoundedRectangle(cornerRadius: 16)
                            .stroke(isSelected ? accentColor.opacity(0.6) : Color.clear, lineWidth: 1.5)
                    )
            )
        }
        .buttonStyle(.plain)
        .animation(.spring(response: 0.25), value: isSelected)
    }

    private var accentColor: Color {
        switch market {
        case .tr:     return Color(hex: "#FF4444")  // Türk bayrağı kırmızısı
        case .us:     return Color(hex: "#4488FF")  // Mavi
        case .crypto: return Color(hex: "#F7931A")  // Bitcoin turuncu
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// MARK: - Market Badge (diğer ekranlarda kullanmak için küçük etiket)
// ─────────────────────────────────────────────────────────────────────────────

struct MarketBadge: View {
    let market: TradingMarket

    var body: some View {
        HStack(spacing: 4) {
            Text(market.flag)
                .font(.caption2)
            Text(market.rawValue)
                .font(.caption2.weight(.semibold))
                .foregroundColor(badgeColor)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(badgeColor.opacity(0.12))
        .cornerRadius(6)
    }

    private var badgeColor: Color {
        switch market {
        case .tr:     return Color(hex: "#FF4444")
        case .us:     return Color(hex: "#4488FF")
        case .crypto: return Color(hex: "#F7931A")
        }
    }
}

#Preview {
    MarketSelectionView(isOnboarding: true)
        .environmentObject(UserPreferences())
}
