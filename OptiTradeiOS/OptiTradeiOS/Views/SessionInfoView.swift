import SwiftUI

// ─────────────────────────────────────────────────────────────────────────────
// MARK: - Canlı Seans Paneli (Dashboard'a gömülü kompakt kart)
// ─────────────────────────────────────────────────────────────────────────────

struct SessionBannerCard: View {
    let session: SessionInfo
    @State private var showDetail = false

    var body: some View {
        Button { showDetail = true } label: {
            HStack(spacing: 14) {
                // Sol: ikon + nabız animasyonu
                ZStack {
                    Circle()
                        .fill(Color(hex: session.sessionColor).opacity(0.2))
                        .frame(width: 46, height: 46)
                    Image(systemName: session.sessionIcon)
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundColor(Color(hex: session.sessionColor))
                }

                // Orta: seans adı + açıklama
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 6) {
                        if session.sessionCode == "OVERLAP" {
                            Text("⚡")
                        }
                        Text(session.sessionName)
                            .font(.subheadline.bold())
                            .foregroundColor(.white)
                    }
                    Text(session.sessionDescription)
                        .font(.caption2)
                        .foregroundColor(.white.opacity(0.5))
                        .lineLimit(1)
                }

                Spacer()

                // Sağ: volatilite çarpanı + sonraki seans
                VStack(alignment: .trailing, spacing: 3) {
                    Text("×\(session.volatilityMultiplier, specifier: "%.1f")")
                        .font(.headline.monospacedDigit().bold())
                        .foregroundColor(Color(hex: session.sessionColor))
                    Text("\(session.nextSessionMinutes)dk")
                        .font(.caption2.monospacedDigit())
                        .foregroundColor(.white.opacity(0.4))
                }

                Image(systemName: "chevron.right")
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.3))
            }
            .padding(14)
            .background(
                RoundedRectangle(cornerRadius: 16)
                    .fill(Color(hex: session.sessionColor).opacity(0.08))
                    .overlay(
                        RoundedRectangle(cornerRadius: 16)
                            .stroke(Color(hex: session.sessionColor).opacity(0.25), lineWidth: 1)
                    )
            )
        }
        .buttonStyle(.plain)
        .sheet(isPresented: $showDetail) {
            SessionDetailSheet(session: session)
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// MARK: - Detay Sheet
// ─────────────────────────────────────────────────────────────────────────────

struct SessionDetailSheet: View {
    let session: SessionInfo
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ZStack {
                Color(hex: "0A0E1A").ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 20) {
                        // Başlık kartı
                        headerCard

                        // Matematiksel sinyal göstergeleri
                        signalGaugesCard

                        // Seans ağırlıkları
                        weightsCard

                        // Seans sinyalleri
                        if !session.sessionSignals.isEmpty {
                            signalsCard
                        }

                        // Sonraki seans
                        nextSessionCard

                        // Para birimleri
                        if !session.sessionCurrencies.isEmpty {
                            currenciesCard
                        }

                        // Tüm seanslar tablosu
                        allSessionsTable
                    }
                    .padding()
                }
            }
            .navigationTitle("Seans Analizi")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Kapat") { dismiss() }
                        .foregroundColor(.cyan)
                }
            }
        }
    }

    // ── Başlık ────────────────────────────────────────────────────────────────

    private var headerCard: some View {
        VStack(spacing: 12) {
            ZStack {
                Circle()
                    .fill(Color(hex: session.sessionColor).opacity(0.15))
                    .frame(width: 72, height: 72)
                Image(systemName: session.sessionIcon)
                    .font(.system(size: 32))
                    .foregroundColor(Color(hex: session.sessionColor))
            }

            Text(session.sessionName)
                .font(.title2.bold())
                .foregroundColor(.white)

            Text(session.sessionDescription)
                .font(.subheadline)
                .foregroundColor(.white.opacity(0.6))
                .multilineTextAlignment(.center)

            HStack(spacing: 16) {
                statBadge(label: "Volatilite", value: String(format: "×%.1f", session.volatilityMultiplier),
                          color: Color(hex: session.sessionColor))
                statBadge(label: "Seans Skoru", value: String(format: "%.0f/100", session.sessionAdjustedScore),
                          color: .cyan)
                statBadge(label: "Güven", value: String(format: "%%%.0f", session.confidence * 100),
                          color: .purple)
            }
        }
        .padding(20)
        .background(sectionBG)
    }

    // ── Sinyal Göstergeleri ───────────────────────────────────────────────────

    private var signalGaugesCard: some View {
        VStack(alignment: .leading, spacing: 14) {
            sectionTitle("Matematiksel Sinyal Analizi")

            VStack(spacing: 10) {
                signalBar(label: "RSI Sinyali",    value: session.rsiSignal,      icon: "waveform.path.ecg")
                signalBar(label: "MACD Sinyali",   value: session.macdSignal,     icon: "chart.line.uptrend.xyaxis")
                signalBar(label: "Hacim Sinyali",  value: session.volumeSignal,   icon: "chart.bar.fill")
                signalBar(label: "Kırılım Sinyali",value: session.breakoutSignal, icon: "bolt.fill")
            }

            Divider().background(Color.white.opacity(0.1))

            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Birleşik Ham Sinyal")
                        .font(.caption).foregroundColor(.white.opacity(0.5))
                    Text("\(session.compositeRaw, specifier: "%+.3f")")
                        .font(.headline.monospacedDigit())
                        .foregroundColor(session.compositeRaw >= 0 ? .green : .red)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 4) {
                    Text("Normalize [0–1]")
                        .font(.caption).foregroundColor(.white.opacity(0.5))
                    Text("\(session.compositeNorm, specifier: "%.3f")")
                        .font(.headline.monospacedDigit()).foregroundColor(.cyan)
                }
            }
        }
        .padding(16)
        .background(sectionBG)
    }

    // ── Ağırlık Tablosu ───────────────────────────────────────────────────────

    private var weightsCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            sectionTitle("Seans Sinyal Ağırlıkları")
            Text("Bu seansta göstergeler aşağıdaki ağırlıklarla değerlendirilir:")
                .font(.caption).foregroundColor(.white.opacity(0.45))

            HStack(spacing: 0) {
                weightCell(label: "RSI",    value: weightForSession(session.sessionCode).rsi)
                weightCell(label: "MACD",   value: weightForSession(session.sessionCode).macd)
                weightCell(label: "Hacim",  value: weightForSession(session.sessionCode).volume)
                weightCell(label: "Kırılım",value: 0.15)
            }
            .background(Color.white.opacity(0.04))
            .clipShape(RoundedRectangle(cornerRadius: 10))
        }
        .padding(16)
        .background(sectionBG)
    }

    // ── Sinyal Mesajları ──────────────────────────────────────────────────────

    private var signalsCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            sectionTitle("Anlık Seans Sinyalleri")
            ForEach(session.sessionSignals, id: \.self) { signal in
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: "circle.fill")
                        .font(.system(size: 5))
                        .foregroundColor(Color(hex: session.sessionColor))
                        .padding(.top, 6)
                    Text(signal)
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.75))
                }
            }
        }
        .padding(16)
        .background(sectionBG)
    }

    // ── Sonraki Seans ─────────────────────────────────────────────────────────

    private var nextSessionCard: some View {
        HStack {
            Image(systemName: "clock.arrow.circlepath")
                .foregroundColor(.orange)
            VStack(alignment: .leading, spacing: 2) {
                Text("Sonraki Geçiş")
                    .font(.caption).foregroundColor(.white.opacity(0.5))
                Text(session.nextSessionLabel)
                    .font(.subheadline.bold()).foregroundColor(.white)
            }
            Spacer()
            Text("\(session.nextSessionMinutes) dakika")
                .font(.headline.monospacedDigit())
                .foregroundColor(.orange)
        }
        .padding(16)
        .background(sectionBG)
    }

    // ── Para Birimleri ────────────────────────────────────────────────────────

    private var currenciesCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            sectionTitle("Bu Seansta En Aktif")
            ScrollView(.horizontal, showsIndicators: false) {
                HStack {
                    ForEach(session.sessionCurrencies, id: \.self) { cur in
                        Text(cur)
                            .font(.caption.bold())
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .background(Color(hex: session.sessionColor).opacity(0.15))
                            .foregroundColor(Color(hex: session.sessionColor))
                            .clipShape(Capsule())
                    }
                }
            }
        }
        .padding(16)
        .background(sectionBG)
    }

    // ── Tüm Seanslar Tablosu ─────────────────────────────────────────────────

    private var allSessionsTable: some View {
        VStack(alignment: .leading, spacing: 10) {
            sectionTitle("Seans Takvimi (Türkiye Saati)")

            VStack(spacing: 0) {
                ForEach(sessionRows, id: \.code) { row in
                    HStack(spacing: 12) {
                        Circle()
                            .fill(Color(hex: row.color))
                            .frame(width: 8, height: 8)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(row.name).font(.caption.bold()).foregroundColor(.white)
                            Text(row.hours).font(.caption2.monospacedDigit()).foregroundColor(.white.opacity(0.4))
                        }
                        Spacer()
                        Text("×\(row.mult, specifier: "%.1f")")
                            .font(.caption.monospacedDigit().bold())
                            .foregroundColor(Color(hex: row.color))
                    }
                    .padding(.vertical, 8)
                    .padding(.horizontal, 12)
                    .background(row.code == session.sessionCode
                                ? Color(hex: row.color).opacity(0.1)
                                : Color.clear)

                    if row.code != sessionRows.last?.code {
                        Divider().background(Color.white.opacity(0.06))
                    }
                }
            }
            .background(Color.white.opacity(0.03))
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
        .padding(16)
        .background(sectionBG)
    }

    // ── Yardımcılar ───────────────────────────────────────────────────────────

    private var sectionBG: some View {
        RoundedRectangle(cornerRadius: 16)
            .fill(Color.white.opacity(0.04))
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.white.opacity(0.07), lineWidth: 1))
    }

    @ViewBuilder
    private func sectionTitle(_ text: String) -> some View {
        Text(text).font(.subheadline.bold()).foregroundColor(.white.opacity(0.8))
    }

    @ViewBuilder
    private func statBadge(label: String, value: String, color: Color) -> some View {
        VStack(spacing: 4) {
            Text(value).font(.subheadline.bold().monospacedDigit()).foregroundColor(color)
            Text(label).font(.caption2).foregroundColor(.white.opacity(0.4))
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 10)
        .background(color.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }

    @ViewBuilder
    private func signalBar(label: String, value: Double, icon: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: icon)
                .font(.caption)
                .frame(width: 16)
                .foregroundColor(.white.opacity(0.5))
            Text(label)
                .font(.caption)
                .foregroundColor(.white.opacity(0.6))
                .frame(width: 110, alignment: .leading)

            GeometryReader { geo in
                ZStack(alignment: value >= 0 ? .leading : .trailing) {
                    RoundedRectangle(cornerRadius: 3).fill(Color.white.opacity(0.07))
                    RoundedRectangle(cornerRadius: 3)
                        .fill(value >= 0 ? Color.green : Color.red)
                        .frame(width: geo.size.width * abs(value) / 2)
                        .offset(x: value >= 0 ? geo.size.width / 2 : 0)
                }
            }
            .frame(height: 8)

            Text("\(value, specifier: "%+.2f")")
                .font(.caption2.monospacedDigit())
                .foregroundColor(value >= 0 ? .green : .red)
                .frame(width: 44, alignment: .trailing)
        }
    }

    @ViewBuilder
    private func weightCell(label: String, value: Double) -> some View {
        VStack(spacing: 4) {
            Text("\(value * 100, specifier: "%.0f")%")
                .font(.subheadline.bold().monospacedDigit())
                .foregroundColor(.cyan)
            Text(label)
                .font(.caption2)
                .foregroundColor(.white.opacity(0.5))
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 10)
    }

    private struct WeightSet { let rsi: Double; let macd: Double; let volume: Double }
    private func weightForSession(_ code: String) -> WeightSet {
        switch code {
        case "OVERLAP": return WeightSet(rsi: 0.22, macd: 0.38, volume: 0.35)
        case "NY":      return WeightSet(rsi: 0.25, macd: 0.38, volume: 0.32)
        case "LONDON":  return WeightSet(rsi: 0.30, macd: 0.38, volume: 0.28)
        case "ASIA":    return WeightSet(rsi: 0.45, macd: 0.25, volume: 0.20)
        default:        return WeightSet(rsi: 0.50, macd: 0.20, volume: 0.15)
        }
    }

    private struct SessionRow { let code: String; let name: String; let hours: String; let mult: Double; let color: String }
    private var sessionRows: [SessionRow] { [
        SessionRow(code: "ASIA",    name: "Asya",           hours: "03:00 – 12:00", mult: 0.65, color: "00CCAA"),
        SessionRow(code: "LONDON",  name: "Londra",         hours: "10:00 – 19:00", mult: 1.20, color: "3399FF"),
        SessionRow(code: "OVERLAP", name: "Çakışma ⚡",     hours: "15:00 – 19:00", mult: 1.80, color: "FF4444"),
        SessionRow(code: "NY",      name: "New York",       hours: "15:00 – 00:00", mult: 1.40, color: "FF8800"),
        SessionRow(code: "CLOSED",  name: "Kapalı",         hours: "00:00 – 03:00", mult: 0.30, color: "666666"),
    ]}
}

// ─────────────────────────────────────────────────────────────────────────────
// MARK: - Tam Sayfa Görünüm (isteğe bağlı)
// ─────────────────────────────────────────────────────────────────────────────

struct SessionInfoView: View {
    @State private var sessionInfo: SessionInfo?
    @State private var isLoading = false
    @State private var timer: Timer?

    var body: some View {
        ZStack {
            Color(hex: "0A0E1A").ignoresSafeArea()
            if isLoading && sessionInfo == nil {
                ProgressView("Seans yükleniyor...")
                    .foregroundColor(.white.opacity(0.6))
            } else if let info = sessionInfo {
                SessionDetailSheet(session: info)
            }
        }
        .task {
            await fetchSession()
            // Her 60 saniyede otomatik güncelle
            timer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { _ in
                Task { await fetchSession() }
            }
        }
        .onDisappear { timer?.invalidate() }
    }

    private func fetchSession() async {
        isLoading = true
        sessionInfo = try? await APIService.shared.getSessionInfo()
        isLoading = false
    }
}
