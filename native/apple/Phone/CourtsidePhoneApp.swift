import SwiftUI
import WebKit
import WatchConnectivity

@main
struct CourtsidePhoneApp: App {
    @StateObject private var bridge = PhoneBridge()
    var body: some Scene {
        WindowGroup { PhoneView(bridge: bridge).preferredColorScheme(.dark) }
    }
}

struct PhoneView: View {
    @ObservedObject var bridge: PhoneBridge
    @AppStorage("courtsideServer") private var address = ""
    var body: some View {
        VStack(spacing: 8) {
            HStack {
                TextField("https://your-courtside-server", text: $address)
                    .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                Button("Connect") { bridge.connect(address) }
            }.padding(.horizontal)
            if !bridge.message.isEmpty { Text(bridge.message).font(.caption).foregroundStyle(.secondary) }
            BrowserView(webView: bridge.webView)
        }.onAppear { if !address.isEmpty { bridge.connect(address) } }
    }
}

struct BrowserView: UIViewRepresentable {
    let webView: WKWebView
    func makeUIView(context: Context) -> WKWebView { webView }
    func updateUIView(_ uiView: WKWebView, context: Context) {}
}

final class PhoneBridge: NSObject, ObservableObject, WCSessionDelegate, WKNavigationDelegate {
    @Published var message = "Open a session to enable Watch scoring."
    let webView = WKWebView(frame: .zero, configuration: WKWebViewConfiguration())
    private var serverOrigin: URL?

    override init() {
        super.init()
        webView.navigationDelegate = self
        webView.allowsBackForwardNavigationGestures = true
        if WCSession.isSupported() {
            WCSession.default.delegate = self
            WCSession.default.activate()
        }
    }

    func connect(_ address: String) {
        guard let url = URL(string: address.trimmingCharacters(in: .whitespacesAndNewlines)),
              let host = url.host, !host.isEmpty, url.user == nil, url.password == nil,
              url.scheme == "https" || (url.scheme == "http" && host.hasSuffix(".local")) else {
            message = "Enter an HTTPS server URL (or a .local HTTP server for local development)."
            return
        }
        serverOrigin = url
        webView.load(URLRequest(url: url))
        message = "Sign in or enter your access token in Settings, then open a session."
    }

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url, let server = serverOrigin else {
            decisionHandler(.cancel); return
        }
        let allowed = url.scheme == server.scheme && url.host == server.host && url.port == server.port
        decisionHandler(allowed ? .allow : .cancel)
    }

    func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
        if let error { DispatchQueue.main.async { self.message = error.localizedDescription } }
    }
    func sessionDidBecomeInactive(_ session: WCSession) {}
    func sessionDidDeactivate(_ session: WCSession) { session.activate() }

    func session(_ session: WCSession, didReceiveMessage message: [String: Any],
                 replyHandler: @escaping ([String: Any]) -> Void) {
        guard let action = message["action"] as? String, ["state", "point", "undo"].contains(action) else {
            replyHandler(["ok": false, "error": "Unsupported Watch command."]); return
        }
        DispatchQueue.main.async {
            // Web code checks the current session, identity, revision, and request ID.
            // Credentials remain in the web view and are never sent to the Watch.
            self.webView.callAsyncJavaScript(
                "if (!window.courtsideWatch) return JSON.stringify({ok:false,error:'Open Courtside in the iPhone app first.'}); return JSON.stringify(await window.courtsideWatch(command));",
                arguments: ["command": message], in: nil, in: .page
            ) { result in
                switch result {
                case .success(let value):
                    guard let text = value as? String, let data = text.data(using: .utf8),
                          let response = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                        replyHandler(["ok": false, "error": "Invalid response from Courtside."]); return
                    }
                    replyHandler(response)
                case .failure(let error):
                    replyHandler(["ok": false, "error": error.localizedDescription])
                }
            }
        }
    }
}
