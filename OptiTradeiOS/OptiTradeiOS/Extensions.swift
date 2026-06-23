import SwiftUI
import CryptoKit

// MARK: - Color Extensions
extension Color {
    init(hex: String) {
        var h = hex.trimmingCharacters(in: .whitespacesAndNewlines)
        if h.hasPrefix("#") { h.removeFirst() }
        let num = UInt64(h, radix: 16) ?? 0
        let r = Double((num >> 16) & 0xFF) / 255
        let g = Double((num >> 8)  & 0xFF) / 255
        let b = Double(num         & 0xFF) / 255
        self.init(red: r, green: g, blue: b)
    }
    
    static let adaptiveBackground = Color(UIColor { $0.userInterfaceStyle == .dark ? UIColor(red: 0.06, green: 0.06, blue: 0.07, alpha: 1) : UIColor(red: 0.97, green: 0.97, blue: 0.98, alpha: 1) })
    static let adaptiveCard = Color(UIColor { $0.userInterfaceStyle == .dark ? UIColor(red: 0.12, green: 0.12, blue: 0.14, alpha: 1) : UIColor.white })
    static let adaptiveText = Color(UIColor { $0.userInterfaceStyle == .dark ? UIColor.white : UIColor.black })
    static let adaptiveSecondary = Color(UIColor { $0.userInterfaceStyle == .dark ? UIColor(red: 0.7, green: 0.7, blue: 0.71, alpha: 1) : UIColor(red: 0.3, green: 0.3, blue: 0.31, alpha: 1) })
}

// MARK: - String Extensions
extension String {
    func sha256() -> String {
        let inputData = Data(self.utf8)
        let hashedData = SHA256.hash(data: inputData)
        let hashString = hashedData.compactMap { String(format: "%02x", $0) }.joined()
        return hashString
    }

    static func randomNonceString(length: Int = 32) -> String {
        precondition(length > 0)
        var randomBytes = [UInt8](repeating: 0, count: length)
        let result = SecRandomCopyBytes(kSecRandomDefault, randomBytes.count, &randomBytes)
        if result != errSecSuccess {
            fatalError("Unable to generate nonce. SecRandomCopyBytes failed with OSStatus \(result)")
        }

        let charset: [Character] =
            Array("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")

        let nonce = randomBytes.map { byte in
            charset[Int(byte) % charset.count]
        }

        return String(nonce)
    }
}

// MARK: - View Animation Extensions
extension View {
    func smoothSlideInAnimation(delay: Double = 0) -> some View {
        self
            .transition(.asymmetric(
                insertion: .move(edge: .leading).combined(with: .opacity),
                removal: .move(edge: .trailing).combined(with: .opacity)
            ))
            .animation(.easeInOut(duration: 0.4).delay(delay), value: UUID())
    }
    
    func scaleAndFadeAnimation(scale: Double = 0.95) -> some View {
        self
            .scaleEffect(scale)
            .opacity(0.5)
            .onAppear {
                withAnimation(.easeOut(duration: 0.5)) {
                    self.scaleEffect(1.0)
                    self.opacity(1.0)
                }
            }
    }
    
    func cardShadow() -> some View {
        self
            .shadow(color: Color.black.opacity(0.08), radius: 12, x: 0, y: 4)
    }
}

// MARK: - Accessibility Extensions
extension View {
    func accessibilityElement(children: AccessibilityChildBehavior, role: AccessibilityRole? = nil, label: String? = nil) -> some View {
        self
            .accessibility(children: children)
            .if(let label) { view in
                view.accessibility(label: Text(label))
            }
    }
    
    @ViewBuilder
    func `if`<Content: View>(_ condition: Bool, transform: (Self) -> Content) -> some View {
        if condition {
            transform(self)
        } else {
            self
        }
    }
}

// MARK: - Performance Extensions
extension View {
    func deferredRendering() -> some View {
        self.onAppear { }
    }
}
