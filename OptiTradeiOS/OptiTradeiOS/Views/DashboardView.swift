import SwiftUI

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
    @EnvironmentObject private var session: UserSession
    @EnvironmentObject private var preferences: UserPreferences
    @State private var sessionInfo: SessionInfo?

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Seans banner — her zaman üstte görünür
                if let info = sessionInfo {
                    SessionBannerCard(session: info)
                        .padding(.horizontal)
                        .padding(.top, 8)
                        .padding(.bottom, 4)
                }
                headerControls
                Divider()
                content
                
                if !session.isPremium {
                    AdBannerPlaceholder()
                }
            }
            .navigationTitle("Piyasa Taraması")
            .navigationBarTitleDisplayMode(.large)
            .toolbar { toolbarItems }
            .task {
                await vm.scan()
                sessionInfo = try? await APIService.shared.getSessionInfo()
            }
        }
    }

    private var headerControls: some View {
        VStack(spacing: 8) {
            Picker("Piyasa", selection: $vm.selectedMarket) {
                Text("BIST").tag("bist")
                Text("Kripto").tag("crypto")
            }
            .pickerStyle(.segmented)
            .padding(.horizontal)
            .onChange(of: vm.selectedMarket) { Task { await vm.scan() } }

            HStack {
                Menu {
                    ForEach(ScanSort.allCases, id: \.self) { s in
                        Button {
                            vm.sortBy = s
                        } label: {
                            if vm.sortBy == s {
                                Label(s.rawValue, systemImage: "checkmark")
                            } else {
                                Text(s.rawValue)
                            }
                        }
                    }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "arrow.up.arrow.down")
                            .font(.caption)
                        Text(vm.sortBy.rawValue)
                            .font(.caption)
                    }
                    .foregroundColor(.accentColor)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(Color.accentColor.opacity(0.1))
                    .clipShape(Capsule())
                }

                Spacer()

                if let t = vm.lastScanned {
                    Text("Son tarama: \(t, style: .time)")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }
            .padding(.horizontal)
            .padding(.bottom, 8)
        }
        .padding(.top, 8)
        .background(Color(.systemBackground))
    }

    @ViewBuilder
    private var content: some View {
        if vm.isLoading {
            ScrollView {
                LazyVStack(spacing: 10) {
                    ForEach(0..<5, id: \.self) { _ in
                        SkeletonResultCard()
                            .padding(.horizontal)
                    }
                }
                .padding(.vertical, 8)
            }
        } else if let error = vm.errorMessage {
            Spacer()
            VStack(spacing: 12) {
                Image(systemName: "wifi.exclamationmark")
                    .font(.system(size: 44))
                    .foregroundColor(.orange)
                Text(error)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)
                Button("Tekrar Dene") { Task { await vm.scan() } }
                    .foregroundColor(.accentColor)
            }
            Spacer()
        } else if let scan = vm.scanResult {
            resultsView(scan)
        } else {
            Spacer()
            EmptyStateView(
                icon: "chart.bar.xaxis",
                title: "Tarama Başlatılıyor",
                subtitle: "Veriler yükleniyor..."
            )
            Spacer()
        }
    }

    private func resultsView(_ scan: ScanResult) -> some View {
        ScrollView {
            LazyVStack(spacing: 10) {
                ScanSummaryBanner(scan: scan)
                    .padding(.horizontal)
                    .padding(.top, 4)

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
                        ? "En Yüksek Puanlı Hisseler" : "Nötr"
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

                Text("\(scan.totalScanned) sembol tarandı")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .padding(.vertical, 4)

                VStack(spacing: 4) {
                    Divider()
                    HStack(spacing: 6) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .font(.caption2)
                            .foregroundColor(.orange)
                        Text("Gösterilen sinyaller yatırım tavsiyesi değildir.")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                    Text("Product by Algorix  •  algorix.io")
                        .font(.caption2)
                        .foregroundColor(.secondary.opacity(0.5))
                        .tracking(0.5)
                }
                .padding(.bottom, 16)
            }
            .padding(.vertical, 8)
        }
        .refreshable { await vm.scan() }
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
                    Text("Sektör Analizi")
                        .font(.subheadline.weight(.semibold))
                        .foregroundColor(.white)
                    Text("Hangi sektörde fırsat var?")
                        .font(.caption)
                        .foregroundColor(.gray)
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
            if vm.isLoading {
                ProgressView().tint(.accentColor)
            } else {
                Button { Task { await vm.scan() } } label: {
                    Image(systemName: "arrow.clockwise")
                }
            }
        }
    }
}
