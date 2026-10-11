# Tennis app interface

The interface uses SwingVision's public dark app screens as a visual reference: black backgrounds, green navigation, video session cards, stroke colors, shot statistics, and court diagrams. Courtside branding and the existing local processing model are retained.

Reference: https://developer.apple.com/news/?id=0pg4dthn
Recording workflow reference: https://swing.vision/hardware

## Implemented

- Sessions landing screen with search, session-type and processing-state filters, sorting, and grid/list views.
- Home with recent sessions, weekly activity, a locally persisted session goal, and stroke counts.
- Session review tabs for video/shots, statistics, calibrated player positions, and match tools; keyboard tab navigation and playback-speed selection.
- Desktop navigation and a fixed mobile tab bar.
- Existing uploads, junior consent, live analysis, settings, academy accounts, coach feedback, and report exports remain connected.
- Missing real media displays an unavailable state instead of a synthetic demonstration.
- Persistent tennis scorekeeping, provisional ground-contact line review, rally candidates, and private highlight exports. See [match tools](match-tools.md).
- Native iPhone/Apple Watch companion source, pending Mac compilation and paired-device verification.

## Limits

This is an adaptation of public references, not verified pixel-for-pixel or feature-for-feature parity with the current native SwingVision app. No proprietary assets or models are bundled. Browser live analysis does not save recordings. Court maps use the existing `court_position` player-at-contact coordinates in metres on a singles court. They do not represent ball bounces. Fully autonomous point-winner recognition, officiating-grade line calling, ball speed, and cloud sharing are not implemented. Rally boundaries are heuristic candidates; scores require confirmed winners and line estimates require confirmed ground contact. Apple Watch source is supplied but has not been compiled or device-tested on this Windows machine. Demo sessions remain explicitly labeled synthetic.

## Validation

Run `npm run check`, `npm run build`, and `npm test`. Regression tests in `web/src/SwingViews.test.tsx` cover filtering, sorting, import/camera actions, goals, calibrated positions, missing media, playback state, and report tab keyboard navigation. Browser screenshots are stored under `artifacts/swingvision-reference/`.

Verified on 2026-10-10: TypeScript check and production build passed; 38 tests passed. Browser checks passed at widths 320, 390, 768, 1024 and 1440. Home, live, progress, coaching, settings and reports had no horizontal overflow at phone and desktop sizes. The existing backend returned healthy with the pose model ready; demo media loaded without a playback error, 0.5x speed applied, and live start remained disabled until processing consent was supplied. Real camera capture and new video analysis were not exercised.

Follow-up match feature verification: see [match-tools.md](match-tools.md) for current test totals, behavior, and remaining limits.
