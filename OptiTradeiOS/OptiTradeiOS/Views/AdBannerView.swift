import SwiftUI
import UIKit

// Not: GoogleMobileAds SDK henüz projede yoksa bu dosya derleme hatası verebilir.
// Eğer hata alırsanız 'import GoogleMobileAds' satırını yorum satırına alıp
// placeholder görünümü kullanabilirsiniz.

/*
import GoogleMobileAds

struct AdBannerView: UIViewControllerRepresentable {
    let adUnitID: String

    func makeUIViewController(context: Context) -> UIViewController {
        let viewController = UIViewController()
        let adSize = GADAdSizeBanner
        let bannerView = GADBannerView(adSize: adSize)

        bannerView.adUnitID = adUnitID
        bannerView.rootViewController = viewController
        bannerView.load(GADRequest())

        viewController.view.addSubview(bannerView)
        bannerView.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            bannerView.centerXAnchor.constraint(equalTo: viewController.view.centerXAnchor),
            bannerView.bottomAnchor.constraint(equalTo: viewController.view.bottomAnchor)
        ])

        return viewController
    }

    func updateUIViewController(_ uiViewController: UIViewController, context: Context) {}
}
*/

// SDK yokken kullanılacak Placeholder (Reklam Alanı)
struct AdBannerPlaceholder: View {
    var body: some View {
        HStack {
            Spacer()
            VStack(spacing: 4) {
                Text("REKLAM")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(.white.opacity(0.4))
                Text("Google AdMob Alanı")
                    .font(.caption2)
                    .foregroundColor(.white.opacity(0.2))
            }
            Spacer()
        }
        .frame(height: 50)
        .background(Color.white.opacity(0.05))
        .overlay(
            Rectangle()
                .stroke(Color.white.opacity(0.1), lineWidth: 1)
        )
    }
}
