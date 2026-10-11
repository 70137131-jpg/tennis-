import SwiftUI
import WatchConnectivity

struct WatchMatch: Decodable {
    struct Config: Decodable { let players: [String] }
    struct Score: Decodable {
        let points: [String]
        let games: [Int]
        let sets: [Int]
        let server: Int
        let winner: Int?
        let points_played: Int
    }
    let session_id: String
    let revision: Int
    let config: Config
    let score: Score
}

@main
struct CourtsideWatchApp: App {
    @StateObject private var model = WatchScoreModel()
    var body: some Scene {
        WindowGroup { WatchScoreView(model: model) }
    }
}

struct WatchScoreView: View {
    @ObservedObject var model: WatchScoreModel
    var body: some View {
        ScrollView {
            VStack(spacing: 10) {
                Text("COURTSIDE").font(.caption2).foregroundStyle(.green)
                if let match = model.match {
                    ForEach(0..<2, id: \.self) { player in
                        Button { model.point(player) } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                Text((match.score.server == player ? "● " : "") + match.config.players[player])
                                    .font(.caption).lineLimit(1)
                                HStack {
                                    Text(match.score.points[player]).font(.title2.bold())
                                    Spacer()
                                    Text("\(match.score.sets[player]) sets · \(match.score.games[player]) games").font(.caption2)
                                }
                            }
                        }.tint(player == 0 ? .green : .blue)
                            .disabled(model.busy || model.hasPending || match.score.winner != nil)
                    }
                    if let winner = match.score.winner {
                        Text("\(match.config.players[winner]) wins").font(.headline)
                    }
                    Button("Undo point") { model.undo() }
                        .disabled(model.busy || model.hasPending || match.score.points_played == 0)
                } else {
                    Image(systemName: "tennisball").font(.largeTitle).foregroundStyle(.green)
                    Text("Open a session in the paired iPhone app.").font(.caption)
                }
                if model.busy { ProgressView() }
                if !model.message.isEmpty { Text(model.message).font(.caption2).foregroundStyle(.secondary) }
                if model.hasPending {
                    Button("Retry last command") { model.retry() }.disabled(model.busy)
                    Text("The last result is unconfirmed. Retry safely before adding another point.").font(.caption2)
                } else {
                    Button("Refresh score") { model.refresh() }.disabled(model.busy)
                }
            }
        }.onAppear { model.refresh() }
    }
}

final class WatchScoreModel: NSObject, ObservableObject, WCSessionDelegate {
    @Published var match: WatchMatch?
    @Published var busy = false
    @Published var message = ""
    @Published var hasPending = false
    private var pending: [String: Any]?

    override init() {
        super.init()
        WCSession.default.delegate = self
        WCSession.default.activate()
    }
    func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {
        DispatchQueue.main.async {
            if let error { self.message = error.localizedDescription }
            else if !self.hasPending { self.refresh() }
        }
    }
    func refresh() { guard !busy, !hasPending else { return }; send(["action": "state"]) }
    func point(_ winner: Int) { mutate("point", winner: winner) }
    func undo() { mutate("undo", winner: nil) }
    func retry() { if let pending, !busy { send(pending) } }

    private func mutate(_ action: String, winner: Int?) {
        guard let match, !busy, !hasPending else { return }
        var command: [String: Any] = ["action": action, "request_id": UUID().uuidString,
                                      "session_id": match.session_id, "revision": match.revision]
        if let winner { command["winner"] = winner }
        pending = command; hasPending = true
        send(command)
    }
    private func send(_ command: [String: Any]) {
        guard WCSession.default.activationState == .activated, WCSession.default.isReachable else {
            message = "Keep the paired iPhone app open and connected."; return
        }
        busy = true; message = ""
        WCSession.default.sendMessage(command, replyHandler: { response in
            DispatchQueue.main.async {
                self.busy = false
                if response["ok"] as? Bool == true,
                   let raw = response["state"], let data = try? JSONSerialization.data(withJSONObject: raw),
                   let value = try? JSONDecoder().decode(WatchMatch.self, from: data) {
                    self.match = value; self.pending = nil; self.hasPending = false
                } else {
                    self.message = response["error"] as? String ?? "Could not update the score."
                    // A known rejection didn't score a point. Unknown transport failures
                    // retain the same request ID so a retry cannot double-count a point.
                    let status = response["status"] as? Int ?? 0
                    if (400..<500).contains(status) {
                        self.pending = nil; self.hasPending = false
                        self.match = nil
                    }
                }
            }
        }, errorHandler: { error in
            DispatchQueue.main.async { self.busy = false; self.message = error.localizedDescription }
        })
    }
}
