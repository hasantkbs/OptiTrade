import SwiftUI
import Charts

struct MiniSparkline: View {
    let points: [ChartPoint]
    let isPositive: Bool

    private var color: Color { isPositive ? .green : .red }

    var body: some View {
        Chart {
            ForEach(Array(points.enumerated()), id: \.offset) { i, p in
                LineMark(
                    x: .value("i", i),
                    y: .value("close", p.close)
                )
                .foregroundStyle(color)
                .interpolationMethod(.catmullRom)
            }
            if let last = points.last, let first = points.first {
                AreaMark(
                    x: .value("i", points.count - 1),
                    yStart: .value("min", min(first.close, last.close) * 0.995),
                    yEnd: .value("close", last.close)
                )
                .foregroundStyle(
                    LinearGradient(
                        colors: [color.opacity(0.3), color.opacity(0.0)],
                        startPoint: .top, endPoint: .bottom
                    )
                )
            }
        }
        .chartXAxis(.hidden)
        .chartYAxis(.hidden)
        .chartLegend(.hidden)
        .frame(height: 44)
    }
}

struct PriceChart: View {
    let chart: ChartResponse
    @State private var selectedPoint: ChartPoint?

    private var isPositive: Bool { chart.changePct >= 0 }
    private var lineColor: Color { isPositive ? .green : .red }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    if let sel = selectedPoint {
                        Text(sel.date)
                            .font(.caption)
                            .foregroundColor(.secondary)
                        Text(String(format: "%.2f", sel.close))
                            .font(.title2.bold())
                    } else if let last = chart.points.last {
                        Text("Güncel")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        Text(String(format: "%.2f", last.close))
                            .font(.title2.bold())
                    }
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text(String(format: "%+.2f%%", chart.changePct))
                        .font(.headline.weight(.semibold))
                        .foregroundColor(lineColor)
                    HStack(spacing: 6) {
                        Text("H: \(String(format: "%.2f", chart.high))")
                        Text("L: \(String(format: "%.2f", chart.low))")
                    }
                    .font(.caption2)
                    .foregroundColor(.secondary)
                }
            }

            Chart {
                ForEach(Array(chart.points.enumerated()), id: \.offset) { i, p in
                    LineMark(
                        x: .value("i", i),
                        y: .value("close", p.close)
                    )
                    .foregroundStyle(lineColor)
                    .interpolationMethod(.catmullRom)
                }
                if let sel = selectedPoint,
                   let idx = chart.points.firstIndex(where: { $0.date == sel.date }) {
                    RuleMark(x: .value("i", idx))
                        .foregroundStyle(Color.secondary.opacity(0.5))
                        .lineStyle(StrokeStyle(dash: [4]))
                    PointMark(
                        x: .value("i", idx),
                        y: .value("close", sel.close)
                    )
                    .foregroundStyle(lineColor)
                    .symbolSize(60)
                }
            }
            .chartXAxis(.hidden)
            .chartYAxis {
                AxisMarks(position: .trailing, values: .automatic(desiredCount: 4)) {
                    AxisValueLabel().font(.caption2).foregroundStyle(Color.secondary)
                }
            }
            .chartOverlay { proxy in
                GeometryReader { geo in
                    Rectangle().fill(Color.clear).contentShape(Rectangle())
                        .gesture(
                            DragGesture(minimumDistance: 0)
                                .onChanged { val in
                                    let x = val.location.x - geo[proxy.plotFrame!].origin.x
                                    if let idx: Int = proxy.value(atX: x) {
                                        let clamped = max(0, min(chart.points.count - 1, idx))
                                        selectedPoint = chart.points[clamped]
                                        HapticService.shared.selection()
                                    }
                                }
                                .onEnded { _ in
                                    withAnimation(.easeOut(duration: 0.3)) { selectedPoint = nil }
                                }
                        )
                }
            }
            .frame(height: 180)
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }
}

struct RSIGauge: View {
    let value: Double

    private var color: Color {
        if value > 70 { return .red }
        if value < 30 { return .green }
        return .orange
    }
    private var label: String {
        if value > 70 { return "Aşırı Alım" }
        if value < 30 { return "Aşırı Satım" }
        return "Normal"
    }

    var body: some View {
        VStack(spacing: 8) {
            ZStack {
                Gauge(value: value, in: 0...100) {
                    EmptyView()
                } currentValueLabel: {
                    Text(String(format: "%.0f", value))
                        .font(.system(size: 18, weight: .bold, design: .rounded))
                        .foregroundColor(color)
                }
                .gaugeStyle(.accessoryCircular)
                .tint(Gradient(colors: [.green, .orange, .red]))
                .scaleEffect(1.4)
            }
            .frame(height: 70)

            Text(label)
                .font(.caption.weight(.medium))
                .foregroundColor(color)
        }
    }
}

struct RSIChart: View {
    let points: [ChartPoint]

    var body: some View {
        let rsiPoints = points.filter { $0.rsi != nil }
        Chart {
            ForEach(Array(rsiPoints.enumerated()), id: \.offset) { i, p in
                LineMark(
                    x: .value("i", i),
                    y: .value("rsi", p.rsi!)
                )
                .foregroundStyle(Color.purple)
                .interpolationMethod(.catmullRom)
            }
            RuleMark(y: .value("ob", 70)).foregroundStyle(.red.opacity(0.5)).lineStyle(StrokeStyle(dash: [4]))
            RuleMark(y: .value("os", 30)).foregroundStyle(.green.opacity(0.5)).lineStyle(StrokeStyle(dash: [4]))
        }
        .chartYScale(domain: 0...100)
        .chartXAxis(.hidden)
        .chartYAxis {
            AxisMarks(values: [0, 30, 70, 100]) {
                AxisValueLabel().font(.caption2).foregroundStyle(Color.secondary)
            }
        }
        .frame(height: 80)
    }
}

struct VolumeChart: View {
    let points: [ChartPoint]
    let isPositive: Bool

    var body: some View {
        Chart {
            ForEach(Array(points.enumerated()), id: \.offset) { i, p in
                BarMark(
                    x: .value("i", i),
                    y: .value("vol", p.volume)
                )
                .foregroundStyle(isPositive ? Color.green.opacity(0.5) : Color.red.opacity(0.5))
            }
        }
        .chartXAxis(.hidden)
        .chartYAxis(.hidden)
        .frame(height: 50)
    }
}
