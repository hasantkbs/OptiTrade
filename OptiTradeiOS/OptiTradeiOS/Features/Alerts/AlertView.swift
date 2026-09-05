import SwiftUI

/// The dedicated Alerts screen — Step 8. Reachable from the account menu
/// on every tab (Section 11: no new root tab). Lists every alert the user
/// owns (`GET /alerts`, no `watchlist_id` filter), supports enabling/
/// disabling, deleting, creating a new alert (Price/Decision types with a
/// verified parameter contract — see `AlertModels.swift`), and an
/// on-demand "Check Now" scan (`POST /alerts/scan`).
struct AlertsView: View {
    @State private var viewModel: AlertViewModel
    @State private var isPresentingCreateForm = false

    init(viewModel: AlertViewModel) {
        _viewModel = State(initialValue: viewModel)
    }

    var body: some View {
        content
            .navigationTitle("Alerts")
            .task { await viewModel.loadIfNeeded() }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        isPresentingCreateForm = true
                    } label: {
                        Label("New Alert", systemImage: "plus")
                    }
                }
                ToolbarItem(placement: .topBarLeading) {
                    scanButton
                }
            }
            .sheet(isPresented: $isPresentingCreateForm) {
                CreateAlertFormView(viewModel: viewModel, onCreated: {})
            }
    }

    @ViewBuilder
    private var scanButton: some View {
        Button {
            Task { await viewModel.scanNow() }
        } label: {
            if viewModel.isScanning {
                ProgressView()
            } else {
                Label("Check Now", systemImage: "arrow.clockwise")
            }
        }
        .disabled(viewModel.isScanning)
        .accessibilityLabel("Check alerts now")
    }

    @ViewBuilder
    private var content: some View {
        switch viewModel.state {
        case .idle, .loading:
            ProgressView("Loading alerts…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)

        case .empty:
            AlertsEmptyStateView()

        case .failed(let message):
            AlertsErrorView(message: message) {
                Task { await viewModel.loadIfNeeded() }
            }

        case .loaded(let alerts):
            AlertsLoadedView(
                alerts: alerts,
                refreshError: viewModel.refreshError,
                mutationError: viewModel.mutationError,
                scanError: viewModel.scanError,
                lastScanSummary: viewModel.lastScanSummary,
                pendingAlertIDs: viewModel.pendingAlertIDs,
                onToggleEnabled: { alertID, enabled in Task { await viewModel.setEnabled(enabled, alertID: alertID) } },
                onDelete: { alertID in Task { await viewModel.deleteAlert(alertID: alertID) } }
            )
            .refreshable { await viewModel.refresh() }
        }
    }
}

private struct AlertsLoadedView: View {
    let alerts: [AlertRule]
    let refreshError: String?
    let mutationError: String?
    let scanError: String?
    let lastScanSummary: AlertScanSummary?
    let pendingAlertIDs: Set<Int>
    let onToggleEnabled: (Int, Bool) -> Void
    let onDelete: (Int) -> Void

    var body: some View {
        List {
            if let refreshError {
                Section {
                    Text(refreshError)
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .accessibilityLabel("Refresh error: \(refreshError)")
                }
            }

            if let mutationError {
                Section {
                    Text(mutationError)
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .accessibilityLabel("Alert error: \(mutationError)")
                }
            }

            if let scanError {
                Section {
                    Text(scanError)
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .accessibilityLabel("Check now error: \(scanError)")
                }
            } else if let lastScanSummary {
                Section {
                    Text("Checked \(lastScanSummary.checkedCount) of \(lastScanSummary.totalAlerts) alerts — \(lastScanSummary.triggeredCount) triggered.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }

            Section {
                ForEach(alerts) { rule in
                    AlertRowView(
                        rule: rule,
                        isPending: pendingAlertIDs.contains(rule.id),
                        onToggleEnabled: { enabled in onToggleEnabled(rule.id, enabled) },
                        onDelete: { onDelete(rule.id) }
                    )
                }
            }
        }
        .listStyle(.insetGrouped)
    }
}
