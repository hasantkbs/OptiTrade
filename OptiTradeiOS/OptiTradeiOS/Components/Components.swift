import SwiftUI

struct ScoreMeter: View {
    let score: Int

    private var color: Color {
        if score >= 63 { return .green }
        if score <= 37 { return .red }
        return .orange
    }

    var body: some View {
        ZStack {
            Circle()
                .stroke(Color.gray.opacity(0.2), lineWidth: 8)
            Circle()
                .trim(from: 0, to: CGFloat(score) / 100)
                .stroke(color, style: StrokeStyle(lineWidth: 8, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .animation(.easeInOut(duration: 0.5), value: score)
            VStack(spacing: 2) {
                Text("\(score)")
                    .font(.system(size: 22, weight: .bold, design: .rounded))
                    .foregroundColor(color)
                Text("puan")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
        }
        .frame(width: 80, height: 80)
    }
}

struct DecisionBadge: View {
    let decisionCode: String
    let decision: String

    private var badgeColor: Color {
        switch decisionCode {
        case "STRONG_BUY":  return .green
        case "BUY":         return Color(red: 0.2, green: 0.8, blue: 0.4)
        case "STRONG_SELL": return .red
        case "SELL":        return Color(red: 1.0, green: 0.4, blue: 0.3)
        default:            return .orange
        }
    }

    private var icon: String {
        switch decisionCode {
        case "STRONG_BUY":  return "arrow.up.circle.fill"
        case "BUY":         return "arrow.up.right.circle.fill"
        case "STRONG_SELL": return "arrow.down.circle.fill"
        case "SELL":        return "arrow.down.left.circle.fill"
        default:            return "minus.circle.fill"
        }
    }

    var body: some View {
        Label(decision, systemImage: icon)
            .font(.caption.weight(.semibold))
            .foregroundColor(badgeColor)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(badgeColor.opacity(0.12))
            .clipShape(Capsule())
    }
}

struct RiskBadge: View {
    let level: String

    private var config: (text: String, color: Color) {
        switch level {
        case "Cok Yuksek": return ("Çok Yüksek Risk", .red)
        case "Yuksek":     return ("Yüksek Risk", .orange)
        case "Orta":       return ("Orta Risk", .yellow)
        default:           return ("Düşük Risk", .green)
        }
    }

    var body: some View {
        Text(config.text)
            .font(.caption2.weight(.medium))
            .foregroundColor(config.color)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(config.color.opacity(0.12))
            .clipShape(Capsule())
    }
}

struct IndicatorRow: View {
    let title: String
    let value: String
    let color: Color

    var body: some View {
        HStack {
            Text(title)
                .font(.subheadline)
                .foregroundColor(.secondary)
            Spacer()
            Text(value)
                .font(.subheadline.weight(.semibold))
                .foregroundColor(color)
        }
        .padding(.vertical, 4)
    }
}

struct SignalRow: View {
    let text: String
    let isLong: Bool

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: isLong ? "arrow.up.right" : "arrow.down.right")
                .font(.caption)
                .foregroundColor(isLong ? .green : .red)
                .padding(.top, 2)
            Text(text)
                .font(.caption)
                .foregroundColor(.primary)
        }
    }
}

struct EmptyStateView: View {
    let icon: String
    let title: String
    let subtitle: String

    var body: some View {
        VStack(spacing: 14) {
            Image(systemName: icon)
                .font(.system(size: 52))
                .foregroundColor(.secondary.opacity(0.6))
            Text(title)
                .font(.headline)
                .foregroundColor(.secondary)
            Text(subtitle)
                .font(.caption)
                .foregroundColor(.secondary.opacity(0.7))
                .multilineTextAlignment(.center)
        }
        .padding()
    }
}

struct SectionHeaderView: View {
    let title: String
    let count: Int
    let color: Color

    var body: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(color)
                .frame(width: 8, height: 8)
            Text(title)
                .font(.title3.bold())
            Text("(\(count))")
                .font(.subheadline)
                .foregroundColor(.secondary)
            Spacer()
        }
        .padding(.top, 8)
    }
}

struct SearchHistoryTag: View {
    let item: SearchHistoryItem
    let onTap: () -> Void
    let onDelete: () -> Void

    private var color: Color {
        switch item.decisionCode {
        case "STRONG_BUY", "BUY": return .green
        case "STRONG_SELL", "SELL": return .red
        default: return .orange
        }
    }

    var body: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(color)
                .frame(width: 6, height: 6)
            Text(item.symbol)
                .font(.caption.weight(.semibold))
                .foregroundColor(.primary)
            Text("\(item.score)")
                .font(.caption2)
                .foregroundColor(.secondary)
            Button(action: onDelete) {
                Image(systemName: "xmark")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundColor(.secondary)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(Color(.tertiarySystemBackground))
        .clipShape(Capsule())
        .onTapGesture(perform: onTap)
    }
}

struct QuickSymbolButton: View {
    let symbol: String
    let displayName: String
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            VStack(spacing: 4) {
                Text(displayName)
                    .font(.caption.weight(.bold))
                    .foregroundColor(.primary)
                Text(symbol)
                    .font(.system(size: 9))
                    .foregroundColor(.secondary)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 10)
            .background(Color(.tertiarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 10))
        }
    }
}

struct SkeletonResultCard: View {
    @State private var phase = false

    var body: some View {
        HStack(spacing: 14) {
            Circle()
                .fill(Color(.tertiarySystemBackground))
                .frame(width: 80, height: 80)
            VStack(alignment: .leading, spacing: 8) {
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color(.tertiarySystemBackground))
                    .frame(width: 90, height: 16)
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color(.tertiarySystemBackground))
                    .frame(width: 130, height: 12)
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color(.tertiarySystemBackground))
                    .frame(width: 70, height: 12)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 8) {
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color(.tertiarySystemBackground))
                    .frame(width: 60, height: 16)
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color(.tertiarySystemBackground))
                    .frame(width: 44, height: 12)
            }
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .opacity(phase ? 0.45 : 1.0)
        .animation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true), value: phase)
        .onAppear { phase = true }
    }
}

struct ScanSummaryBanner: View {
    let scan: ScanResult

    private var buyCount: Int { scan.topBuys.count }
    private var sellCount: Int { scan.topSells.count }
    private var neutralCount: Int { scan.neutral.count }
    private var total: Int { buyCount + sellCount + neutralCount }

    private var avgScore: Double {
        let all = scan.topBuys + scan.topSells + scan.neutral
        guard !all.isEmpty else { return 50 }
        return Double(all.map(\.score).reduce(0, +)) / Double(all.count)
    }

    var body: some View {
        VStack(spacing: 10) {
            HStack(spacing: 0) {
                statPill("AL", count: buyCount, color: .green)
                Divider().frame(height: 36)
                statPill("SAT", count: sellCount, color: .red)
                Divider().frame(height: 36)
                statPill("NÖTR", count: neutralCount, color: .orange)
                Divider().frame(height: 36)
                VStack(spacing: 2) {
                    Text(String(format: "%.0f", avgScore))
                        .font(.system(size: 18, weight: .bold, design: .rounded))
                        .foregroundColor(avgScore >= 63 ? .green : avgScore <= 37 ? .red : .orange)
                    Text("Ort. Puan")
                        .font(.system(size: 9))
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity)
            }

            if total > 0 {
                GeometryReader { geo in
                    HStack(spacing: 0) {
                        Rectangle()
                            .fill(Color.green)
                            .frame(width: geo.size.width * CGFloat(buyCount) / CGFloat(total))
                        Rectangle()
                            .fill(Color.orange)
                            .frame(width: geo.size.width * CGFloat(neutralCount) / CGFloat(total))
                        Rectangle()
                            .fill(Color.red)
                    }
                    .clipShape(Capsule())
                    .frame(height: 6)
                }
                .frame(height: 6)
            }
        }
        .padding(12)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
    }

    private func statPill(_ label: String, count: Int, color: Color) -> some View {
        VStack(spacing: 2) {
            Text("\(count)")
                .font(.system(size: 18, weight: .bold, design: .rounded))
                .foregroundColor(color)
            Text(label)
                .font(.system(size: 9))
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity)
    }
}

struct SectorChip: View {
    let title: String
    let isSelected: Bool
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundColor(isSelected ? .white : .primary)
                .padding(.horizontal, 14)
                .padding(.vertical, 7)
                .background(isSelected ? Color.accentColor : Color(.tertiarySystemBackground))
                .clipShape(Capsule())
        }
    }
}
