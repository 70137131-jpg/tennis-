# Match review, highlights, and Apple Watch

Open a completed session and select **Match & highlights**.

## Scoring

Set the players, first server, best-of-one/three/five format, and advantage or no-ad scoring before the first point. Award a point to its confirmed winner. Courtside calculates 15/30/40, deuce/advantage, games, sets, the seven-point win-by-two tiebreak at 6–6, and the match result. Undo reverses the last point, including a completed game or match. Match settings unlock when all points are undone.

Scores persist in the session's SQLite workspace. Request IDs make retries idempotent, and revisions reject competing edits. A refresh retrieves the authoritative score. The page refreshes every five seconds for changes made on another device. Rally-linked results must be scored in chronological order; undo later results before correcting earlier ones. Points entered from the main scoreboard or Watch are standalone confirmations and are not automatically matched to video rallies.

This is automated scorekeeping from human-confirmed winners. The current video tracker cannot reliably determine the point winner. This implementation does not claim autonomous scoring, doubles player service rotation, configurable match tiebreak formats, or verified parity with SwingVision.

## Rally candidates and highlight export

Contacts separated by more than four seconds begin a new rally candidate. Candidates have a short lead-in and tail, are ordered chronologically, and remain within the session timeline. Missed detections can split a rally; drills can resemble points. Review each candidate before scoring or exporting.

Filter candidates by stroke, sort by time or shot count, select up to 50 candidates totaling five minutes, and choose **Export highlights**. The server trims and concatenates the privacy-processed video into an H.264 MP4, without audio. Exports preserve chronological order, use signed private media links, and retain academy workspace authorization. One export runs at a time per workspace. An interrupted export is marked failed on server restart. Session deletion and retention cleanup remove its score, reviews, export jobs, and videos.

Synthetic demo timelines can exceed the duration of their illustrative clip. Those selections are rejected instead of creating an apparently complete match video. Windows storage paths must remain within the filesystem's supported length; exports are checked for accessibility before reporting completion.

## Provisional line review

Choose **Line review**, pause at a visible ground-contact frame, and step one frame at a time as needed. Calibrate the four outside singles corners in this order: far left, far right, near right, near left. Mark the ball's ground-contact position, choose the singles/doubles court or service box, select an uncertainty margin, and confirm that ground contact is visible. Select **Estimate line call** to save the review.

Court calibration projects a point on the ground plane. It cannot project an airborne ball accurately. The result includes an allowance for the ball footprint; evidence within the selected margin stays **Too close to call**. The selected ±12/25/50 cm margin is a user assumption, not a measured or guaranteed camera accuracy. Calibration error, image blur, and the chosen contact frame can invalidate a result. These are provisional estimates for review, not officiating-grade automatic calls. Court-position diagrams elsewhere in the app still show player positions, not ball bounces.

High-confidence image-space direction changes offer possible bounce frames. Interpolated/weak samples, large time gaps, and turns near shot contacts are excluded. Every candidate remains unverified until visually reviewed. A saved line estimate never automatically awards a point.

## Native companion

[native/apple/README.md](../native/apple/README.md) contains Mac/Xcode setup instructions for the SwiftUI iPhone container and paired Apple Watch scoreboard. The Watch fetches the current score, confirms a point winner, and undoes the last point through the signed-in iPhone web view. Credentials remain on iPhone. Lost replies can be retried with the same command ID. The phone must keep the target session open and connected.

Native source and XcodeGen configuration are included. Compilation, code signing, installation, WatchConnectivity, and paired-device behavior have not been verified in this Windows workspace. Independent Watch networking, HealthKit, camera recording controls, and background scoring are not included.

## Verification

Verified on 2026-10-10:

- 202 Python tests passed, with 88.84% total coverage; scoring and rally/line geometry achieved 100%, match API 94%.
- 46 frontend tests passed; TypeScript, production build, Ruff, and mypy passed.
- Real FFmpeg tests decoded single- and multi-rally exports and checked private download links and byte ranges.
- Academy tests exercised login, CSRF, workspace separation, logout/revocation, signed downloads, and retry behavior.
- Browser score/undo controls and video metadata worked. No horizontal overflow at widths 320, 390, 768, 1024, or 1440.
- Screenshot evidence: `artifacts/swingvision-reference/match-tools-desktop.png` and `match-tools-mobile.png`.

Reference rules: [ITF 2026 Rules of Tennis](https://www.itftennis.com/media/7221/2026-rules-of-tennis-english.pdf). These tests validate scorekeeping and implementation behavior; they do not establish computer-vision accuracy on real match footage or native Watch compatibility.
