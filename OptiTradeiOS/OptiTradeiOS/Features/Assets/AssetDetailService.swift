import Foundation

/// Networking for the Asset Detail / Quant Analysis screen. Talks to the
/// *real* backend contract:
///   - `POST /quant/analyze`  -> PipelineResponse   (required — Technical/
///     Fundamental/News Engines -> Decision Engine -> Risk, one call)
///   - `GET /price/{symbol}`  -> untyped quote dict  (best-effort)
///   - `GET /chart/{symbol}`  -> ChartResponse       (best-effort)
///
/// All three already work with the existing `APIClient`'s Bearer-token
/// injection and 401->refresh handling from Step 1/2 — nothing new was
/// needed there. The three requests are independent of each other, so
/// they run concurrently (Section 25) rather than sequentially.
protocol AssetDetailServicing: Sendable {
    func fetchAssetDetail(symbol: String, assetType: String) async throws -> AssetDetailSummary
}

struct AssetDetailService: AssetDetailServicing {
    private let apiClient: APIClient

    init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    func fetchAssetDetail(symbol: String, assetType: String) async throws -> AssetDetailSummary {
        let quantRequest = try APIRequest<PipelineResponseDTO>(
            path: "quant/analyze",
            method: .post,
            body: QuantAnalysisRequestDTO(symbol: symbol, assetType: assetType)
        )

        async let quantResult = apiClient.send(quantRequest)
        async let priceResult: PriceQuoteDTO? = try? apiClient.send(APIRequest<PriceQuoteDTO>(path: "price/\(symbol)"))
        async let chartResult: ChartResponseDTO? = try? apiClient.send(APIRequest<ChartResponseDTO>(path: "chart/\(symbol)"))

        // The Quant analysis is required — its failure fails the whole
        // fetch. Market data and the chart are best-effort: `try?` above
        // already reduced any failure to `nil`, which becomes an honest
        // "unavailable" section in the domain model rather than blocking
        // the Decision Engine result the screen exists to show.
        let quantDTO = try await quantResult
        let priceDTO = await priceResult
        let chartDTO = await chartResult

        return AssetDetailSummary(
            symbol: quantDTO.symbol,
            quant: QuantAnalysis(dto: quantDTO),
            marketData: priceDTO.map(MarketQuote.init(dto:)),
            chart: chartDTO.map(AssetPriceChart.init(dto:))
        )
    }
}
