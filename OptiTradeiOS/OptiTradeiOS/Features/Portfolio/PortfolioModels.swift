import Foundation

// MARK: - Wire DTOs
//
// Match `backend/portfolio/models.py` exactly. No custom `CodingKeys` —
// property names are plain camelCase and rely on `APICoding`'s
// `convertFromSnakeCase` strategy (see Core/Authentication/AuthModels.swift
// for why mixing the two breaks decoding).

/// Wire shape of `portfolio.models.Portfolio`. Only the fields this screen
/// actually needs — `created_at` is ignored.
struct PortfolioDTO: Decodable, Sendable {
    let id: Int?
    let owner: String
    let name: String
    let baseCurrency: String
}

/// Wire shape of `portfolio.models.PositionAnalytics`.
struct PositionAnalyticsDTO: Decodable, Sendable {
    let symbol: String
    let quantity: Double
    let averageCost: Double
    let currentPrice: Double
    let costBasis: Double
    let currentValue: Double
    let unrealizedPnl: Double
    let unrealizedPnlPct: Double
    let realizedPnl: Double
    let weightPct: Double
    let sector: String
    let country: String
    let currency: String
}

/// Wire shape of `portfolio.models.PortfolioDashboard`. `allocation`,
/// `risk`, and `recommendations` are intentionally not modeled here — this
/// screen (Step 3) only shows summary + holdings.
struct PortfolioDashboardDTO: Decodable, Sendable {
    let portfolioId: Int
    let cashBalance: Double
    let totalValue: Double
    let realizedPnl: Double
    let unrealizedPnl: Double
    let positions: [PositionAnalyticsDTO]
}

// MARK: - Domain models

/// One holding, as actually returned by `GET /portfolios/{id}/dashboard`.
struct PortfolioPosition: Sendable, Equatable, Identifiable {
    var id: String { symbol }
    let symbol: String
    let quantity: Double
    let averageCost: Double
    let currentPrice: Double
    let costBasis: Double
    let currentValue: Double
    let unrealizedPnL: Double
    let unrealizedPnLPct: Double
    let realizedPnL: Double
    let weightPct: Double
    let sector: String
    let country: String
    let currency: String

    init(dto: PositionAnalyticsDTO) {
        symbol = dto.symbol
        quantity = dto.quantity
        averageCost = dto.averageCost
        currentPrice = dto.currentPrice
        costBasis = dto.costBasis
        currentValue = dto.currentValue
        unrealizedPnL = dto.unrealizedPnl
        unrealizedPnLPct = dto.unrealizedPnlPct
        realizedPnL = dto.realizedPnl
        weightPct = dto.weightPct
        sector = dto.sector
        country = dto.country
        currency = dto.currency
    }
}

/// Everything `PortfolioView` needs to render — assembled from one
/// `Portfolio` (for its id/name/currency) and its `PortfolioDashboard`
/// (for the actual financial figures and holdings). Never contains a value
/// that wasn't actually returned by the backend.
struct PortfolioSummary: Sendable, Equatable {
    let portfolioID: Int
    let name: String
    let baseCurrency: String
    let cashBalance: Double
    let totalValue: Double
    let realizedPnL: Double
    let unrealizedPnL: Double
    let positions: [PortfolioPosition]

    init(portfolio: PortfolioDTO, dashboard: PortfolioDashboardDTO) {
        portfolioID = dashboard.portfolioId
        name = portfolio.name
        baseCurrency = portfolio.baseCurrency
        cashBalance = dashboard.cashBalance
        totalValue = dashboard.totalValue
        realizedPnL = dashboard.realizedPnl
        unrealizedPnL = dashboard.unrealizedPnl
        positions = dashboard.positions.map(PortfolioPosition.init(dto:))
    }
}
