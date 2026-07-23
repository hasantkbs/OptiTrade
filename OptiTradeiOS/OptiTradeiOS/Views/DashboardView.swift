import SwiftUI

enum DashboardMode {
    case scan, aiHub
}

enum ScanSort: String, CaseIterable {
    case score = "Puana Göre"
    case velocity = "Değişime Göre"
    case rsi = "RSI'ya Göre"
}

@MainActor
final class DashboardViewModel: ObservableObject {
    @Published var scanResult: ScanResult?
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var selectedMarket: String = "bist"
    @Published var sortBy: ScanSort = .score
    @Published var lastScanned: Date?

    func scan() async {
        isLoading = true
        errorMessage = nil
        do {
            scanResult = try await (selectedMarket == "bist"
                ? APIService.shared.scanBIST()
                : APIService.shared.scanCrypto())
            lastScanned = Date()
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    func sorted(_ list: [AnalysisResult]) -> [AnalysisResult] {
        switch sortBy {
        case .score:    return list.sorted { $0.score > $1.score }
        case .velocity: return list.sorted { abs($0.indicators.priceVelocity) > abs($1.indicators.priceVelocity) }
        case .rsi:      return list.sorted { ($0.indicators.rsi ?? 50) > ($1.indicators.rsi ?? 50) }
        }
    }
}

struct DashboardView: View {
    @StateObject private var vm = DashboardViewModel()
    @StateObject private var aiHubVM = AIHubViewModel()
    @EnvironmentObject private var session: UserSession
    @EnvironmentObject private var preferences: UserPreferences
    @State private var sessionInfo: SessionInfo?
    @State private var mode: DashboardMode = .scan

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Picker(L("Görünüm"), selection: $mode) {
                    Text(L("Piyasa Taraması")).tag(DashboardMode.scan)
                    Text(L("AI Önerileri")).tag(DashboardMode.aiHub)
                }
                .pickerStyle(.segmented)
                .padding(.horizontal)
                .padding(.vertical, 8)
                .background(Color(.systemBackground))

                if mode == .scan {
                    headerControls
                    Divider()
                    content

                    if !session.isPremium {
                        AdBannerPlaceholder()
                    }
                } else {
                    AIHubView(vm: aiHubVM)
                }
            }
            .navigationTitle(mode == .scan ? L("Piyasa Taraması") : L("AI Önerileri"))
            .navigationBarTitleDisplayMode(.large)
            .toolbar { toolbarItems }
            .task {
                await vm.scan()
                sessionInfo = try? await APIService.shared.getSessionInfo()
            }
        }
    }

    private var headerControls: some View {
        HStack(spacing: 12) {
            Picker(L("Piyasa"), selection: $vm.selectedMarket) {
                Text(L("Hisse")).tag("bist")
                Text(L("Kripto")).tag("crypto")
            }
            .pickerStyle(.segmented)
            .frame(width: 160)
            .onChange(of: vm.selectedMarket) { Task { await vm.scan() } }

            Menu {
                ForEach(ScanSort.allCases, id: \.self) { s in
                    Button {
                        vm.sortBy = s
                    } label: {
                        if vm.sortBy == s {
                            Label(L(s.rawValue), systemImage: "checkmark")
                        } else {
                            Text(L(s.rawValue))
                        }
                    }
                }
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "arrow.up.arrow.down")
                        .font(.caption)
                    Text(L(vm.sortBy.rawValue))
                        .font(.caption)
                }
                .foregroundColor(.accentColor)
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(Color.accentColor.opacity(0.1))
                .clipShape(Capsule())
            }

            Spacer()
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(Color(.systemBackground))
    }

    private var content: some View {
        ScrollView {
            LazyVStack(spacing: 10) {
                if let info = sessionInfo {
                    SessionBannerCard(session: info)
                        .padding(.horizontal)
                        .padding(.top, 8)
                }
                MarketNewsTicker()

                if vm.isLoading {
                    ForEach(0..<5, id: \.self) { _ in
                        SkeletonResultCard()
                            .padding(.horizontal)
                    }
                } else if let error = vm.errorMessage {
                    VStack(spacing: 12) {
                        Image(systemName: "wifi.exclamationmark")
                            .font(.system(size: 44))
                            .foregroundColor(.orange)
                        Text(error)
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal)
                        Button(L("Tekrar Dene")) { Task { await vm.scan() } }
                            .foregroundColor(.accentColor)
                    }
                    .padding(.top, 60)
                } else if let scan = vm.scanResult {
                    resultsContent(scan)
                } else {
                    EmptyStateView(
                        icon: "chart.bar.xaxis",
                        title: "Tarama Başlatılıyor",
                        subtitle: "Veriler yükleniyor..."
                    )
                    .padding(.top, 60)
                }
            }
            .padding(.vertical, 8)
        }
        .refreshable { await vm.scan() }
    }

    @ViewBuilder
    private func resultsContent(_ scan: ScanResult) -> some View {
        ScanSummaryBanner(scan: scan)
            .padding(.horizontal)
            .padding(.top, 4)

        if let t = vm.lastScanned {
            Text("\(L("Son tarama")): \(t, style: .time)")
                .font(.caption2)
                .foregroundColor(.secondary)
                .padding(.horizontal)
        }

        // Sektör Fırsat Kartı
        NavigationLink(destination: SectorOpportunityView()
            .environmentObject(preferences)) {
            SectorOpportunityMiniCard()
        }
        .buttonStyle(.plain)
        .padding(.horizontal)

        if !scan.topBuys.isEmpty {
            SectionHeaderView(title: "AL Sinyalleri", count: scan.topBuys.count, color: .green)
                .padding(.horizontal)
            ForEach(vm.sorted(scan.topBuys)) { r in
                NavigationLink(destination: AnalysisDetailView(result: r)) {
                    ResultCardView(result: r)
                }
                .buttonStyle(.plain)
                .padding(.horizontal)
            }
        }

        if !scan.topSells.isEmpty {
            SectionHeaderView(title: "SAT Sinyalleri", count: scan.topSells.count, color: .red)
                .padding(.horizontal)
            ForEach(vm.sorted(scan.topSells)) { r in
                NavigationLink(destination: AnalysisDetailView(result: r)) {
                    ResultCardView(result: r)
                }
                .buttonStyle(.plain)
                .padding(.horizontal)
            }
        }

        let showNeutral = session.showNeutralInScan || (scan.topBuys.isEmpty && scan.topSells.isEmpty)
        if showNeutral && !scan.neutral.isEmpty {
            let title = (scan.topBuys.isEmpty && scan.topSells.isEmpty)
                ? L("En Yüksek Puanlı Hisseler") : L("Nötr")
            let color: Color = (scan.topBuys.isEmpty && scan.topSells.isEmpty) ? .blue : .orange
            let neutralSorted = scan.neutral.sorted { $0.score > $1.score }
            let displayed = (scan.topBuys.isEmpty && scan.topSells.isEmpty)
                ? Array(neutralSorted.prefix(8)) : neutralSorted
            SectionHeaderView(title: title, count: displayed.count, color: color)
                .padding(.horizontal)
            ForEach(displayed) { r in
                NavigationLink(destination: AnalysisDetailView(result: r)) {
                    ResultCardView(result: r)
                }
                .buttonStyle(.plain)
                .padding(.horizontal)
            }
        }

        Text("\(scan.totalScanned) \(L("sembol tarandı"))")
            .font(.caption)
            .foregroundColor(.secondary)
            .padding(.vertical, 4)

        VStack(spacing: 4) {
            Divider()
            HStack(spacing: 6) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.caption2)
                    .foregroundColor(.orange)
                Text(L("Gösterilen sinyaller yatırım tavsiyesi değildir."))
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
            HStack(spacing: 4) {
                Text("Product by AlgorixStudio  •")
                    .foregroundColor(.secondary.opacity(0.5))
                Link("algorixstudio.com", destination: URL(string: "https://algorixstudio.com")!)
                    .foregroundColor(.secondary.opacity(0.8))
            }
            .font(.caption2)
            .tracking(0.5)
        }
        .padding(.bottom, 16)
    }

    // MARK: - SectorOpportunityMiniCard

    struct SectorOpportunityMiniCard: View {
        var body: some View {
            HStack(spacing: 12) {
                Text("🏦")
                    .font(.title2)
                    .frame(width: 42, height: 42)
                    .background(Color(hex: "#00D4FF").opacity(0.1))
                    .cornerRadius(10)
                VStack(alignment: .leading, spacing: 3) {
                    Text(L("Sektör Analizi"))
                        .font(.subheadline.weight(.semibold))
                        .foregroundColor(.primary)
                    Text(L("Hangi sektörde fırsat var?"))
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.caption)
                    .foregroundColor(Color(hex: "#00D4FF"))
            }
            .padding(14)
            .background(Color(hex: "#00D4FF").opacity(0.06))
            .overlay(
                RoundedRectangle(cornerRadius: 14)
                    .stroke(Color(hex: "#00D4FF").opacity(0.2), lineWidth: 1)
            )
            .cornerRadius(14)
        }
    }

    @ToolbarContentBuilder
    private var toolbarItems: some ToolbarContent {
        ToolbarItem(placement: .navigationBarTrailing) {
            if mode == .scan {
                if vm.isLoading {
                    ProgressView().tint(.accentColor)
                } else {
                    Button { Task { await vm.scan() } } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                }
            } else {
                if aiHubVM.isLoading {
                    ProgressView().tint(.accentColor)
                } else {
                    Button { Task { await aiHubVM.analyze() } } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                }
            }
        }
    }
}

// MARK: - AdMob Placeholder
struct AdBannerPlaceholder: View {
    var body: some View {
        HStack {
            Spacer()
            VStack(spacing: 4) {
                Text(L("REKLAM"))
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(.secondary.opacity(0.7))
                Text(L("Google AdMob Alanı"))
                    .font(.caption2)
                    .foregroundColor(.secondary.opacity(0.5))
            }
            Spacer()
        }
        .frame(height: 50)
        .background(Color.primary.opacity(0.05))
        .overlay(
            Rectangle()
                .stroke(Color.primary.opacity(0.1), lineWidth: 1)
        )
    }
}
