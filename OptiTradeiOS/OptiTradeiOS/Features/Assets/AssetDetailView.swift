import SwiftUI

/// The Asset Detail / Quant Analysis screen — Step 5. Reached by
/// selecting an asset from Search results or the Watchlist (Step 4's
/// `AssetSelection`, still the strongly-typed entry point). Presents the
/// real deterministic backend pipeline: Technical/Fundamental/News
/// Engines -> Decision Engine -> Risk, via `POST /quant/analyze`, plus
/// best-effort market data and a price chart. No LLM-authored content is
/// shown here — see `PipelineResponseDTO`'s doc comment.
struct AssetDetailView: View {
    let selection: AssetSelection
    let watchlistViewModel: WatchlistScreenViewModel
    @State private var detailViewModel: AssetDetailViewModel

    init(
        selection: AssetSelection,
        watchlistViewModel: WatchlistScreenViewModel,
        makeDetailViewModel: () -> AssetDetailViewModel
    ) {
        self.selection = selection
        self.watchlistViewModel = watchlistViewModel
        _detailViewModel = State(initialValue: makeDetailViewModel())
    }

    /// `market == "CRYPTO"` (from Step 4's real per-market symbol
    /// directory) maps to the backend's own `asset_type` values
    /// (`AnalysisRequest`/`QuantAnalysisRequest`: `"stock" | "crypto"`).
    /// A Watchlist-only selection carries no `market` at all, so it falls
    /// back to the backend's own default, `"stock"` — not a guess, the
    /// same default `QuantAnalysisRequest.asset_type` already declares.
    private var assetType: String {
        selection.market == "CRYPTO" ? "crypto" : "stock"
    }

    var body: some View {
        content
            .navigationTitle(selection.symbol)
            .navigationBarTitleDisplayMode(.inline)
            .task { detailViewModel.load(symbol: selection.symbol, assetType: assetType) }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    watchlistButton
                }
            }
    }

    @ViewBuilder
    private var content: some View {
        switch detailViewModel.state {
        case .idle, .loading:
            ProgressView("Analyzing \(selection.symbol)…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)

        case .failed(let message):
            AssetDetailErrorView(message: message) {
                detailViewModel.load(symbol: selection.symbol, assetType: assetType)
            }

        case .loaded(let summary):
            AssetDetailLoadedView(
                selection: selection,
                summary: summary,
                refreshError: detailViewModel.refreshError
            )
            .refreshable { await detailViewModel.refresh(assetType: assetType) }
        }
    }

    @ViewBuilder
    private var watchlistButton: some View {
        let symbol = selection.symbol
        let isPending = watchlistViewModel.pendingSymbols.contains(symbol)
        let isMember = watchlistViewModel.isInWatchlist(symbol)

        Button {
            Task {
                if isMember {
                    await watchlistViewModel.remove(symbol: symbol)
                } else {
                    await watchlistViewModel.add(symbol: symbol)
                }
            }
        } label: {
            if isPending {
                ProgressView()
            } else {
                Image(systemName: isMember ? "star.fill" : "star")
                    .foregroundStyle(isMember ? Color.yellow : Color.primary)
            }
        }
        .disabled(isPending)
        .accessibilityLabel(isMember ? "Remove \(symbol) from watchlist" : "Add \(symbol) to watchlist")
    }
}

private struct AssetDetailErrorView: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        ContentUnavailableView {
            Label("Couldn't Load Analysis", systemImage: "exclamationmark.triangle")
        } description: {
            Text(message)
        } actions: {
            Button("Try Again", action: retry)
        }
    }
}

// MARK: - Loaded state

private struct AssetDetailLoadedView: View {
    let selection: AssetSelection
    let summary: AssetDetailSummary
    let refreshError: String?

    var body: some View {
        List {
            Section {
                AssetHeaderView(selection: selection, quote: summary.marketData)
            }
            .listRowInsets(EdgeInsets())
            .listRowBackground(Color.clear)

            if let refreshError {
                Section {
                    Text(refreshError)
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .accessibilityLabel("Refresh error: \(refreshError)")
                }
            }

            if let chart = summary.chart {
                Section {
                    AssetPriceChartSectionView(chart: chart)
                }
            }

            Section {
                QuantDecisionCardView(quant: summary.quant)
            }
            .listRowInsets(EdgeInsets())
            .listRowBackground(Color.clear)

            Section("Engine Votes") {
                ForEach(summary.quant.engineVotes) { vote in
                    EngineVoteRow(vote: vote)
                }
            }

            if let technical = summary.quant.technical {
                Section("Technical Analysis") {
                    EngineDetailSectionView(title: "Technical", vote: technical)
                }
            }

            if let fundamental = summary.quant.fundamental {
                Section("Fundamental Analysis") {
                    EngineDetailSectionView(title: "Fundamental", vote: fundamental)
                }
            }

            if let news = summary.quant.news {
                Section("News Analysis") {
                    EngineDetailSectionView(title: "News", vote: news)
                }
            }

            Section("Risk") {
                RiskSectionView(risk: summary.quant.risk)
            }

            if !summary.quant.evidence.isEmpty {
                Section("Why?") {
                    EvidenceSectionView(evidence: summary.quant.evidence)
                }
            }
        }
        .listStyle(.insetGrouped)
    }
}
