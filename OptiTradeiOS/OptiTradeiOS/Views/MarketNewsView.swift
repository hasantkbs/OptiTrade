import SwiftUI

@MainActor
final class MarketNewsViewModel: ObservableObject {
    @Published var response: TopicNewsResponse?
    @Published var isLoading = false
    @Published var errorMessage: String?

    func load() async {
        isLoading = true
        errorMessage = nil
        do {
            response = try await APIService.shared.fetchMarketNews()
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}

struct MarketNewsView: View {
    @StateObject private var vm = MarketNewsViewModel()

    var body: some View {
        Group {
            if vm.isLoading && vm.response == nil {
                VStack {
                    Spacer()
                    ProgressView(L("Haberler yükleniyor..."))
                    Spacer()
                }
            } else if let error = vm.errorMessage, vm.response == nil {
                VStack(spacing: 12) {
                    Spacer()
                    Image(systemName: "wifi.exclamationmark")
                        .font(.system(size: 44))
                        .foregroundColor(.orange)
                    Text(error)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal)
                    Button(L("Tekrar Dene")) { Task { await vm.load() } }
                        .foregroundColor(.accentColor)
                    Spacer()
                }
            } else if let response = vm.response, !response.headlines.isEmpty {
                List(response.headlines) { headline in
                    headlineRow(headline)
                        .listRowInsets(EdgeInsets(top: 10, leading: 16, bottom: 10, trailing: 16))
                }
                .listStyle(.plain)
                .refreshable { await vm.load() }
            } else {
                EmptyStateView(
                    icon: "newspaper",
                    title: L("Haber bulunamadı"),
                    subtitle: L("Daha sonra tekrar deneyin.")
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .navigationTitle(L("Piyasa Haberleri"))
        .navigationBarTitleDisplayMode(.inline)
        .task { await vm.load() }
    }

    private func headlineRow(_ headline: TopicNewsHeadline) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Circle()
                .fill(headline.sentimentColor)
                .frame(width: 8, height: 8)
                .padding(.top, 5)
            VStack(alignment: .leading, spacing: 4) {
                Text(headline.title)
                    .font(.subheadline)
                    .foregroundColor(.primary)
                HStack(spacing: 6) {
                    Text(headline.source)
                        .font(.caption2)
                        .foregroundColor(.secondary)
                    if let date = headline.publishedDate {
                        Text("•").font(.caption2).foregroundColor(.secondary)
                        Text(date, style: .relative)
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// MARK: - Market News Ticker (Tarama sayfası üstünde kaydırılabilir şerit)
// ─────────────────────────────────────────────────────────────────────────────

struct MarketNewsTicker: View {
    @StateObject private var vm = MarketNewsViewModel()

    var body: some View {
        Group {
            if let headlines = vm.response?.headlines, !headlines.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Label(L("Gündem"), systemImage: "newspaper.fill")
                            .font(.caption.weight(.semibold))
                            .foregroundColor(.secondary)
                        Spacer()
                        NavigationLink(L("Tümü")) {
                            MarketNewsView()
                        }
                        .font(.caption2)
                    }
                    .padding(.horizontal)

                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 10) {
                            ForEach(headlines.prefix(10)) { headline in
                                tickerCard(headline)
                            }
                        }
                        .padding(.horizontal)
                        .padding(.bottom, 4)
                    }
                }
                .padding(.top, 6)
            }
        }
        .task { await vm.load() }
    }

    private func tickerCard(_ headline: TopicNewsHeadline) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 4) {
                Circle().fill(headline.sentimentColor).frame(width: 6, height: 6)
                Text(headline.source)
                    .font(.caption2)
                    .foregroundColor(.secondary)
                    .lineLimit(1)
            }
            Text(headline.title)
                .font(.caption)
                .foregroundColor(.primary)
                .lineLimit(3)
                .multilineTextAlignment(.leading)
            Spacer(minLength: 0)
        }
        .padding(10)
        .frame(width: 220, height: 90, alignment: .topLeading)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}
