// OptiTrade — AIHubView
// HybridTradingEngine tabanlı, canlı AI ticaret önerilerini gösteren ana ekran.

import SwiftUI

@MainActor
final class AIHubViewModel: ObservableObject {
    @Published var recommendations: [TradeRecommendation] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    private let fallbackSymbols = ["BTC-USD", "AAPL", "THYAO.IS"]
    private let maxSymbols = 10

    /// Re-read on every `analyze()` call so a symbol added to the watchlist
    /// mid-session shows up on the next refresh without recreating the view.
    private var watchlistSymbols: [String] {
        let symbols = UserSession.shared.watchlist().map(\.symbol)
        return symbols.isEmpty ? fallbackSymbols : Array(symbols.prefix(maxSymbols))
    }

    func analyze() async {
        isLoading = true
        errorMessage = nil
        do {
            recommendations = try await APIService.shared.analyzeSignals(symbols: watchlistSymbols)
            if recommendations.isEmpty {
                errorMessage = APIError.noRecommendations.localizedDescription
            }
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}

struct AIHubView: View {
    @StateObject private var vm = AIHubViewModel()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    if vm.isLoading && vm.recommendations.isEmpty {
                        loadingState
                    } else if let error = vm.errorMessage, vm.recommendations.isEmpty {
                        errorState(error)
                    } else {
                        ForEach(vm.recommendations) { rec in
                            TradeRecommendationCard(recommendation: rec)
                        }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.top, 12)
                .padding(.bottom, 24)
            }
            .background(Color(.systemGroupedBackground).ignoresSafeArea())
            .navigationTitle("AI Hub")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        Task { await vm.analyze() }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .disabled(vm.isLoading)
                }
            }
            .refreshable { await vm.analyze() }
            .task {
                if vm.recommendations.isEmpty { await vm.analyze() }
            }
        }
    }

    // MARK: - Loading

    private var loadingState: some View {
        VStack(spacing: 20) {
            VStack(spacing: 8) {
                ProgressView()
                    .scaleEffect(1.2)
                Text("AI piyasayı analiz ediyor...")
                    .font(.subheadline.weight(.medium))
                    .foregroundColor(.secondary)
                Text("İlk analiz birkaç saniye sürebilir")
                    .font(.caption)
                    .foregroundColor(.secondary.opacity(0.7))
            }
            .padding(.top, 24)
            .padding(.bottom, 4)

            ForEach(0..<3, id: \.self) { _ in
                ShimmerCardPlaceholder()
            }
        }
    }

    // MARK: - Error

    private func errorState(_ message: String) -> some View {
        VStack(spacing: 14) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 36))
                .foregroundColor(.orange)
            Text(message)
                .font(.subheadline)
                .multilineTextAlignment(.center)
                .foregroundColor(.secondary)
            Button {
                Task { await vm.analyze() }
            } label: {
                Label("Tekrar Dene", systemImage: "arrow.clockwise")
                    .font(.subheadline.weight(.semibold))
            }
            .buttonStyle(.borderedProminent)
        }
        .padding(.top, 60)
        .padding(.horizontal, 24)
    }
}

// MARK: - Trade Recommendation Card

struct TradeRecommendationCard: View {
    let recommendation: TradeRecommendation

    private var accentColor: Color { recommendation.signal.color }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider().padding(.horizontal, 16)
            priceRiskBand
            Divider().padding(.horizontal, 16)
            commentarySection
        }
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 18))
        .overlay(
            RoundedRectangle(cornerRadius: 18)
                .strokeBorder(accentColor.opacity(0.25), lineWidth: 1)
        )
        .shadow(color: .black.opacity(0.15), radius: 8, y: 4)
    }

    // AI İçgörü Kartı: sembol + güven skoru + sinyal yönü

    private var header: some View {
        HStack(alignment: .center, spacing: 14) {
            ScoreMeter(score: recommendation.confidenceScore)

            VStack(alignment: .leading, spacing: 6) {
                Text(recommendation.symbol)
                    .font(.title3.weight(.bold))
                DecisionBadge(
                    decisionCode: recommendation.signal.rawValue,
                    decision: recommendation.signal.displayName
                )
                Text(recommendation.marketRegimeDisplayName)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            Spacer()
        }
        .padding(16)
    }

    // Fiyat ve Risk Bandı: ATR bazlı Giriş / Stop-Loss / Take-Profit seviyeleri

    private var priceRiskBand: some View {
        VStack(spacing: 10) {
            priceRow(label: "Take-Profit 2", value: recommendation.takeProfit2,
                     color: .green, icon: "arrow.up.circle.fill", emphasis: true)
            priceRow(label: "Take-Profit 1", value: recommendation.takeProfit1,
                     color: Color(red: 0.2, green: 0.8, blue: 0.4), icon: "arrow.up.circle")
            priceRow(label: "Giriş Fiyatı", value: recommendation.entryPrice,
                     color: .primary, icon: "scope", emphasis: true)
            priceRow(label: "Stop-Loss", value: recommendation.stopLoss,
                     color: .red, icon: "arrow.down.circle.fill", emphasis: true)
        }
        .padding(16)
    }

    private func priceRow(label: String, value: Double, color: Color, icon: String, emphasis: Bool = false) -> some View {
        HStack {
            Image(systemName: icon)
                .foregroundColor(color)
                .frame(width: 20)
            Text(label)
                .font(emphasis ? .subheadline.weight(.semibold) : .subheadline)
                .foregroundColor(emphasis ? .primary : .secondary)
            Spacer()
            Text(formatPrice(value))
                .font(emphasis ? .subheadline.weight(.bold) : .subheadline.weight(.medium))
                .foregroundColor(color)
                .monospacedDigit()
        }
    }

    // AI Yorum Alanı: trader_commentary

    private var commentarySection: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "quote.opening")
                .font(.title3)
                .foregroundColor(accentColor.opacity(0.6))
            Text(recommendation.traderCommentary)
                .font(.system(.subheadline, design: .serif).italic())
                .foregroundColor(.primary.opacity(0.9))
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(16)
        .background(accentColor.opacity(0.06))
    }

    private func formatPrice(_ v: Double) -> String {
        v >= 1000 ? String(format: "%.2f", v) : String(format: "%.4f", v)
    }
}

// MARK: - Shimmer Loading Placeholder

/// Basit, kendine yeten bir "nefes alan" (pulse) shimmer efekti — AI analiz
/// sürerken kart benzeri placeholder'lar üzerinde kullanılır.
private struct PulseShimmerModifier: ViewModifier {
    @State private var isAnimating = false

    func body(content: Content) -> some View {
        content
            .opacity(isAnimating ? 0.35 : 0.85)
            .animation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true), value: isAnimating)
            .onAppear { isAnimating = true }
    }
}

private extension View {
    func pulseShimmer() -> some View { modifier(PulseShimmerModifier()) }
}

private struct ShimmerCardPlaceholder: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 14) {
                Circle()
                    .fill(Color.gray.opacity(0.25))
                    .frame(width: 80, height: 80)
                VStack(alignment: .leading, spacing: 8) {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.gray.opacity(0.25))
                        .frame(width: 90, height: 16)
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.gray.opacity(0.2))
                        .frame(width: 70, height: 20)
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.gray.opacity(0.15))
                        .frame(width: 100, height: 10)
                }
                Spacer()
            }
            RoundedRectangle(cornerRadius: 4).fill(Color.gray.opacity(0.18)).frame(height: 12)
            RoundedRectangle(cornerRadius: 4).fill(Color.gray.opacity(0.18)).frame(height: 12)
            RoundedRectangle(cornerRadius: 4).fill(Color.gray.opacity(0.15)).frame(width: 220, height: 12)
        }
        .padding(16)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 18))
        .pulseShimmer()
    }
}

#Preview {
    AIHubView()
}
