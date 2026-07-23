import SwiftUI
import Charts

struct BacktestPerformanceView: View {
    let symbol: String
    @State private var points: [BacktestPointV2] = []
    @State private var isLoading = true
    @State private var errorMessage: String?
    @State private var selectedView = 0 // 0: Equity, 1: Signals

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("V2 Algoritmik Performans")
                        .font(.headline)
                    Text("Geçmiş Sinyaller ve Portföy Gelişimi")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                Spacer()
                Picker("Görünüm", selection: $selectedView) {
                    Text("Bakiye").tag(0)
                    Text("Sinyaller").tag(1)
                }
                .pickerStyle(.segmented)
                .frame(width: 140)
            }

            if isLoading {
                HStack { Spacer(); ProgressView(); Spacer() }
                    .frame(height: 180)
            } else if let error = errorMessage {
                Text(error)
                    .font(.caption)
                    .foregroundColor(.red)
            } else {
                if selectedView == 0 {
                    equityChart
                } else {
                    priceSignalChart
                }
                metricsGrid
            }
        }
        .padding()
        .background(Color.accentColor.opacity(0.05))
        .cornerRadius(16)
        .task { await loadData() }
    }

    private var equityChart: some View {
        Chart {
            ForEach(points) { point in
                LineMark(
                    x: .value("Zaman", formatDate(point.timestamp)),
                    y: .value("Bakiye", point.equity)
                )
                .interpolationMethod(.catmullRom)
                .foregroundStyle(Color.accentColor.gradient)
                
                AreaMark(
                    x: .value("Zaman", formatDate(point.timestamp)),
                    y: .value("Bakiye", point.equity)
                )
                .interpolationMethod(.catmullRom)
                .foregroundStyle(Color.accentColor.opacity(0.1).gradient)
            }
        }
        .frame(height: 180)
        .chartYScale(domain: .automatic(includesZero: false))
        .chartXAxis(.hidden)
    }

    private var priceSignalChart: some View {
        Chart {
            // Price Line
            ForEach(points) { point in
                LineMark(
                    x: .value("Zaman", formatDate(point.timestamp)),
                    y: .value("Fiyat", point.price)
                )
                .interpolationMethod(.monotone)
                .foregroundStyle(.gray.opacity(0.5))
            }

            // Buy Signals
            ForEach(points.filter { $0.signal == "BUY" }) { point in
                PointMark(
                    x: .value("Zaman", formatDate(point.timestamp)),
                    y: .value("Fiyat", point.price)
                )
                .symbol {
                    Image(systemName: "arrowtriangle.up.fill")
                        .font(.system(size: 10))
                        .foregroundColor(.green)
                }
                .annotation(position: .bottom) {
                    Text("AL")
                        .font(.system(size: 8, weight: .bold))
                        .foregroundColor(.green)
                }
            }

            // Sell Signals
            ForEach(points.filter { $0.signal == "SELL" }) { point in
                PointMark(
                    x: .value("Zaman", formatDate(point.timestamp)),
                    y: .value("Fiyat", point.price)
                )
                .symbol {
                    Image(systemName: "arrowtriangle.down.fill")
                        .font(.system(size: 10))
                        .foregroundColor(.red)
                }
                .annotation(position: .top) {
                    Text("SAT")
                        .font(.system(size: 8, weight: .bold))
                        .foregroundColor(.red)
                }
            }
        }
        .frame(height: 180)
        .chartYScale(domain: .automatic(includesZero: false))
        .chartXAxis(.hidden)
    }

    private var metricsGrid: some View {
        let startEquity = points.first?.equity ?? 1000.0
        let endEquity = points.last?.equity ?? 1000.0
        let totalReturn = (endEquity - startEquity) / startEquity * 100
        
        let buySignals = points.filter { $0.signal == "BUY" }.count
        let sellSignals = points.filter { $0.signal == "SELL" }.count

        return LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
            MetricCard(title: "Toplam Getiri", value: String(format: "%+.1f%%", totalReturn), color: totalReturn >= 0 ? .green : .red)
            MetricCard(title: "Sinyal Sayısı", value: "\(buySignals + sellSignals)", color: .primary)
            MetricCard(title: "Başlangıç", value: "₺\(Int(startEquity))", color: .secondary)
            MetricCard(title: "Son Bakiye", value: "₺\(Int(endEquity))", color: .primary)
        }
    }

    private func loadData() async {
        do {
            points = try await APIService.shared.getBacktestV2(symbol: symbol)
        } catch {
            errorMessage = "Veri yüklenemedi"
        }
        isLoading = false
    }

    private func formatDate(_ iso: String) -> Date {
        let formatter = ISO8601DateFormatter()
        return formatter.date(from: iso) ?? Date()
    }
}

struct MetricCard: View {
    let title: String
    let value: String
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption2)
                .foregroundColor(.secondary)
            Text(value)
                .font(.subheadline.bold())
                .foregroundColor(color)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(Color.white.opacity(0.05))
        .cornerRadius(8)
    }
}
