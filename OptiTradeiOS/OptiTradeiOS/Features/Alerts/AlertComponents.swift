import SwiftUI

/// One alert row. Enabled/disabled is communicated with text + icon, not
/// color alone (Section 16).
struct AlertRowView: View {
    // Named `rule`, not `alert` — a stored property/parameter literally
    // named `alert` is ambiguous against `View.alert(isPresented:content:)`
    // and its sibling overloads (same SDK-collision category as
    // `AlertRule` itself; see that type's doc comment).
    let rule: AlertRule
    let isPending: Bool
    let onToggleEnabled: (Bool) -> Void
    let onDelete: () -> Void

    @State private var showingDeleteConfirmation = false

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    if let symbol = rule.symbol {
                        Text(symbol).font(.headline)
                    }
                    Text(rule.displayName)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                if let parameterSummary = rule.parameterSummary {
                    Text(parameterSummary)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Label(rule.enabled ? "Enabled" : "Disabled", systemImage: rule.enabled ? "bell.fill" : "bell.slash")
                    .font(.caption2)
                    .foregroundStyle(rule.enabled ? Color.green : Color.secondary)
            }

            Spacer()

            if isPending {
                ProgressView()
            } else {
                Toggle("", isOn: Binding(get: { rule.enabled }, set: onToggleEnabled))
                    .labelsHidden()
                    .accessibilityLabel(rule.enabled ? "Disable alert" : "Enable alert")
            }
        }
        .contentShape(Rectangle())
        .swipeActions(edge: .trailing) {
            Button(role: .destructive) {
                showingDeleteConfirmation = true
            } label: {
                Label("Delete", systemImage: "trash")
            }
            .disabled(isPending)
        }
        .confirmationDialog(
            "Delete this alert?",
            isPresented: $showingDeleteConfirmation,
            titleVisibility: .visible
        ) {
            Button("Delete", role: .destructive, action: onDelete)
            Button("Cancel", role: .cancel) {}
        }
        .accessibilityElement(children: .combine)
    }
}

struct AlertsEmptyStateView: View {
    var body: some View {
        ContentUnavailableView(
            "No Alerts Yet",
            systemImage: "bell",
            description: Text("Create an alert to be notified when an asset meets a condition you care about.")
        )
    }
}

struct AlertsErrorView: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        ContentUnavailableView {
            Label("Couldn't Load Alerts", systemImage: "exclamationmark.triangle")
        } description: {
            Text(message)
        } actions: {
            Button("Try Again", action: retry)
        }
    }
}

/// Create-alert form. Restricted to `AlertTypeDTO.creatable` — the exact
/// backend-supported types this app verified the parameter contract for
/// (see `AlertModels.swift`). `lockedSymbol`, when non-nil (Asset Detail
/// integration), fixes the symbol field to the real, currently-selected
/// asset rather than letting the user type an arbitrary one.
struct CreateAlertFormView: View {
    let viewModel: AlertViewModel
    let lockedSymbol: String?
    let onCreated: () -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var symbol: String
    @State private var alertType: AlertTypeDTO = .priceAbove
    @State private var thresholdText: String = ""
    @State private var thresholdPctText: String = ""
    @State private var cooldownMinutes: Int = 60

    init(viewModel: AlertViewModel, lockedSymbol: String? = nil, onCreated: @escaping () -> Void) {
        self.viewModel = viewModel
        self.lockedSymbol = lockedSymbol
        self.onCreated = onCreated
        _symbol = State(initialValue: lockedSymbol ?? "")
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Asset") {
                    if let lockedSymbol {
                        LabeledContent("Symbol", value: lockedSymbol)
                    } else {
                        TextField("Symbol (e.g. AAPL)", text: $symbol)
                            .textInputAutocapitalization(.characters)
                            .autocorrectionDisabled()
                    }
                }

                Section("Alert Type") {
                    Picker("Type", selection: $alertType) {
                        ForEach(AlertTypeDTO.creatable, id: \.self) { type in
                            Text(type.displayName).tag(type)
                        }
                    }
                }

                if alertType.requiresThresholdParameter {
                    Section("Threshold") {
                        TextField("Price threshold", text: $thresholdText)
                            .keyboardType(.decimalPad)
                    }
                } else if alertType.hasOptionalThresholdPctParameter {
                    Section("Threshold (optional)") {
                        TextField("Percent threshold (backend default applies if empty)", text: $thresholdPctText)
                            .keyboardType(.decimalPad)
                    }
                }

                Section("Cooldown") {
                    Stepper("Cooldown: \(cooldownMinutes) min", value: $cooldownMinutes, in: 1...1440, step: 5)
                }

                if let createError = viewModel.createError {
                    Section {
                        Text(createError)
                            .font(.footnote)
                            .foregroundStyle(.red)
                            .accessibilityLabel("Alert creation error: \(createError)")
                    }
                }
            }
            .navigationTitle("New Alert")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    if viewModel.isCreating {
                        ProgressView()
                    } else {
                        Button("Create", action: submit)
                            .disabled(!isFormValid)
                    }
                }
            }
        }
    }

    private var isFormValid: Bool {
        let trimmedSymbol = (lockedSymbol ?? symbol).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedSymbol.isEmpty else { return false }
        if alertType.requiresThresholdParameter {
            return Double(thresholdText) != nil
        }
        return true
    }

    private func submit() {
        let trimmedSymbol = (lockedSymbol ?? symbol).trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        var parameters: [String: Double] = [:]
        if alertType.requiresThresholdParameter, let threshold = Double(thresholdText) {
            parameters["threshold"] = threshold
        }
        if alertType.hasOptionalThresholdPctParameter, let thresholdPct = Double(thresholdPctText) {
            parameters["thresholdPct"] = thresholdPct
        }

        Task {
            let success = await viewModel.createAlert(
                category: alertType.category,
                alertType: alertType,
                symbol: trimmedSymbol,
                parameters: parameters,
                cooldownMinutes: cooldownMinutes
            )
            if success {
                onCreated()
                dismiss()
            }
        }
    }
}
