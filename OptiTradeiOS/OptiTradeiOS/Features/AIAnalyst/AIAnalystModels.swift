import Foundation

// MARK: - Wire DTOs
//
// AI Analyst has exactly one real backend capability: `/quant/analyze`
// (`backend/pipeline/models.py`'s `PipelineResponse`) already carries an
// `explanation: str` field, produced by `explanation_engine.service.
// ExplanationEngine.explain()` — a facade that "never predicts, never
// votes", turns an already-final `DecisionOutput` into plain-language
// text via a Groq LLM call, and *always* falls back to a deterministic,
// non-LLM template (`explanation_engine/fallback.py`) if that call fails
// (`explain()` is documented to never raise). This is the real,
// server-side "Explanation Engine" the spec asks for.
//
// The backend has NO other AI-Analyst-shaped capability:
//   - No dedicated explanation/chat endpoint — `explanation` only ever
//     arrives bundled inside `/quant/analyze`'s response.
//   - No endpoint accepts free-text user input for the LLM to answer —
//     `ExplanationEngine.explain(decision, symbol)` takes only an
//     already-computed `DecisionOutput` and a symbol, nothing else.
//   - No streaming (no SSE/WebSocket route anywhere in `main.py`).
//   - No tools/function-calling.
//   - No conversation/session identifiers.
//   - The API never surfaces `Explanation.provider`/`.model` (groq vs.
//     the deterministic fallback) — only the flattened `.text` reaches
//     the wire, so this client cannot distinguish a real LLM explanation
//     from the template fallback.
// A separate, unrelated system — `POST /api/v1/signals/analyze`
// (`HybridTradingEngine`) — also calls Groq, but to *generate its own*
// BUY/SELL/HOLD recommendation (with entry/stop-loss/take-profit) from
// technical + news data. That is exactly the "LLM becomes a voting
// engine" architecture Step 6 forbids, so it is deliberately not used
// here even though it exists.
//
// Step 6 therefore stops at this real integration boundary: a single,
// read-only "initial explanation" fetched from the existing
// `/quant/analyze` contract. No follow-up-question UI is implemented
// because no backend capability exists to answer one — see the final
// report's "missing backend capabilities" section, not a fabricated
// chat endpoint.
//
// This DTO intentionally overlaps `AssetDetailModels.swift`'s
// `PipelineResponseDTO` (same wire response) but is NOT the same type:
// Step 5's DTO deliberately excludes `explanation` so no LLM-authored
// text can reach the deterministic Quant Analysis screen even by
// accident (Section 26: don't change that screen's meaning). This
// feature needs exactly that one extra field, so it decodes its own,
// smaller projection — reusing `QuantDecision`/`RiskAssessmentDTO`/
// `QuantAnalysisRequestDTO` from Step 5 rather than redefining them.
struct AIAnalystPipelineResponseDTO: Decodable, Sendable {
    let symbol: String
    let decision: QuantDecision
    let confidence: Double
    let expectedReturn: Double
    let expectedVolatility: Double
    let evidence: [String]
    let risk: RiskAssessmentDTO
    let explanation: String
}

// MARK: - Domain models

/// The deterministic analysis the AI Analyst is explaining — the exact
/// fields Section 5 allows, nothing invented.
struct AIAnalystContext: Sendable, Equatable {
    let symbol: String
    let decision: QuantDecision
    let confidence: Double
    let expectedReturn: Double
    let expectedVolatility: Double
    let evidence: [String]
    let risk: RiskSummary

    init(dto: AIAnalystPipelineResponseDTO) {
        symbol = dto.symbol
        decision = dto.decision
        confidence = dto.confidence
        expectedReturn = dto.expectedReturn
        expectedVolatility = dto.expectedVolatility
        evidence = dto.evidence
        risk = RiskSummary(dto: dto.risk)
    }
}

enum AIAnalystMessageRole: String, Sendable, Equatable {
    case user
    case assistant
}

/// One conversation turn. Shaped for a future real back-and-forth (see
/// `AIAnalystPipelineResponseDTO`'s doc comment on why that doesn't exist
/// yet) — today, `role` is always `.assistant`, since there is no backend
/// capability to send a `.user` turn anywhere.
///
/// `id` is derived from `role`+`text` rather than a fresh `UUID()` per
/// construction — same "identifier from real content, not a random value
/// generated at init time" convention every other `Identifiable` domain
/// model in this codebase follows (e.g. `WatchlistAssetItem.id`,
/// `PortfolioPosition.id`). A random per-init UUID would make two
/// messages with identical content compare unequal, which is both wrong
/// and untestable.
struct AIAnalystMessage: Sendable, Equatable, Identifiable {
    var id: String { "\(role.rawValue)-\(text)" }
    let role: AIAnalystMessageRole
    let text: String

    init(role: AIAnalystMessageRole, text: String) {
        self.role = role
        self.text = text
    }
}

/// Everything `AIAnalystView` needs: the deterministic context being
/// explained, plus the one real explanation message the backend produced
/// for it.
struct AIAnalystExplanation: Sendable, Equatable {
    let context: AIAnalystContext
    let message: AIAnalystMessage
}
