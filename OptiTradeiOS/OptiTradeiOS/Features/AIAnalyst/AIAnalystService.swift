import Foundation

/// Networking for the AI Analyst. Talks to the *real* backend contract —
/// the same `POST /quant/analyze` Step 5's `AssetDetailService` calls
/// (see `AIAnalystModels.swift` for why this feature decodes its own,
/// smaller DTO instead of reusing `AssetDetailModels.PipelineResponseDTO`
/// directly). No other endpoint exists for this feature to call.
protocol AIAnalystServicing: Sendable {
    /// `nil` means the backend genuinely produced no explanation text —
    /// a real, honest state (never happens in practice since
    /// `ExplanationEngine.explain()` always falls back to a deterministic
    /// template rather than raising, but handled defensively rather than
    /// assumed away).
    func fetchExplanation(symbol: String, assetType: String) async throws -> AIAnalystExplanation?
}

struct AIAnalystService: AIAnalystServicing {
    private let apiClient: APIClient

    init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    func fetchExplanation(symbol: String, assetType: String) async throws -> AIAnalystExplanation? {
        let request = try APIRequest<AIAnalystPipelineResponseDTO>(
            path: "quant/analyze",
            method: .post,
            body: QuantAnalysisRequestDTO(symbol: symbol, assetType: assetType)
        )
        let dto = try await apiClient.send(request)

        let text = dto.explanation.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return nil }

        return AIAnalystExplanation(
            context: AIAnalystContext(dto: dto),
            message: AIAnalystMessage(role: .assistant, text: text)
        )
    }
}
