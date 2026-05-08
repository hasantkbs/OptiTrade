import Foundation
import UIKit

final class HapticService {
    static let shared = HapticService()
    private init() {}

    func impact(_ style: UIImpactFeedbackGenerator.FeedbackStyle = .medium) {
        UIImpactFeedbackGenerator(style: style).impactOccurred()
    }

    func notification(_ type: UINotificationFeedbackGenerator.FeedbackType) {
        UINotificationFeedbackGenerator().notificationOccurred(type)
    }

    func selection() {
        UISelectionFeedbackGenerator().selectionChanged()
    }

    func signalFeedback(decisionCode: String) {
        switch decisionCode {
        case "STRONG_BUY":  notification(.success)
        case "STRONG_SELL": notification(.error)
        case "BUY", "SELL": impact(.medium)
        default:            impact(.light)
        }
    }
}
