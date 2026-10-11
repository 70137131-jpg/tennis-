# Courtside iPhone + Apple Watch companion

This directory contains a native SwiftUI iPhone container and paired Watch scoreboard. It is source code, not an installed or device-verified build. The current Windows workspace cannot run Xcode.

On a Mac with Xcode and XcodeGen:

1. Run `xcodegen generate` in this directory. Open `CourtsideCompanion.xcodeproj`.
2. Set your Development Team and unique bundle identifiers in both targets. Keep `WKCompanionAppBundleIdentifier` equal to the phone bundle identifier.
3. Build the CourtsidePhone scheme for your iPhone and the CourtsideWatch scheme for its paired Apple Watch. Signing may require an Apple developer account.
4. Build the web frontend (`npm run build`) and run the Courtside server. For phone access, bind it to your LAN interface, explicitly set `COURTSIDE_TOKEN`, and use HTTPS or a `.local` HTTP hostname for development. Do not use `127.0.0.1` from the phone; that refers to the phone itself. Local-network permission is declared; general insecure network loads are not enabled.
5. Enter the server's URL in the iPhone app. Enter the token in the web Settings screen or sign into an academy account. Open the desired session. Keep the iPhone app open.
6. Refresh the Watch score. Tap the player who won the point, or undo the last point. The server handles games, deuce, sets, and tiebreaks. Watch controls confirm winners; they do not infer outcomes from motion sensors.

Commands use WatchConnectivity immediate messages and the iPhone's existing authenticated web view. Tokens and cookies are never copied to the Watch. Request IDs and revisions protect against duplicate delivery and conflicting edits. If a reply is lost, retry the same command; do not create a fresh point until its result is confirmed. Changing the session on iPhone invalidates stale Watch commands.

Device validation still required: signing, installation, paired-device reachability, lost replies/retries, session switching, account expiration, app backgrounding, and Watch accessibility. Camera start/stop, HealthKit, complications, background scoring, and independent Watch network access are not included.

References:
- https://developer.apple.com/documentation/watchconnectivity
- https://developer.apple.com/documentation/watchconnectivity/wcsession/sendmessage(_:replyhandler:errorhandler:)
- https://github.com/yonaskolb/XcodeGen/blob/master/Docs/ProjectSpec.md
