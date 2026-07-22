import SwiftUI
import WebKit

struct TradingViewChart: UIViewRepresentable {
    let symbol: String
    let theme: String // "light" or "dark"

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.backgroundColor = .clear
        webView.isOpaque = false
        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {
        let html = generateHTML()
        uiView.loadHTMLString(html, baseURL: URL(string: "https://www.tradingview.com"))
    }

    private func generateHTML() -> String {
        // TradingView Symbol Mapping
        // Mapping our format (BTC-USD, THYAO.IS) to TradingView (BINANCE:BTCUSDT, BIST:THYAO)
        let tvSymbol = mapSymbol(symbol)
        
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
            <style>
                body, html { margin: 0; padding: 0; width: 100%; height: 100%; background-color: transparent; }
                #tradingview_widget { width: 100%; height: 100vh; }
            </style>
        </head>
        <body>
            <div id="tradingview_widget"></div>
            <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
            <script type="text/javascript">
            new TradingView.widget({
                "autosize": true,
                "symbol": "\(tvSymbol)",
                "interval": "60",
                "timezone": "Etc/UTC",
                "theme": "\(theme)",
                "style": "1",
                "locale": "tr",
                "toolbar_bg": "#f1f3f6",
                "enable_publishing": false,
                "allow_symbol_change": true,
                "container_id": "tradingview_widget",
                "hide_side_toolbar": false,
                "save_image": false,
                "backgroundColor": "rgba(0, 0, 0, 0)"
            });
            </script>
        </body>
        </html>
        """
    }

    private func mapSymbol(_ s: String) -> String {
        let upper = s.uppercased()
        if upper.hasSuffix(".IS") {
            return "BIST:" + upper.replacingOccurrences(of: ".IS", with: "")
        }
        if upper.hasSuffix("-USD") {
            let base = upper.replacingOccurrences(of: "-USD", with: "")
            return "BINANCE:" + base + "USDT"
        }
        if upper.contains(":") { return upper }
        // Default assume US
        return "NASDAQ:" + upper
    }
}
