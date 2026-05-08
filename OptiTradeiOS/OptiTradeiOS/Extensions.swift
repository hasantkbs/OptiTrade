import SwiftUI
import CryptoKit

// Paylaşılan Color(hex:) extension — tüm view'lar buradan kullanır
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
}
extension String {
    func sha256() -> String {
        let inputData = Data(self.utf8)
        let hashedData = SHA256.hash(data: inputData)
        let hashString = hashedData.compactMap { String(format: "%02x", $0) }.joined()
        return hashString
    }

    static func randomNonceString(length: Int = 32) -> String {
// ...

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
