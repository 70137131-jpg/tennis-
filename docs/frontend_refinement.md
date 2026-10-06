# Frontend refinement — 2026-10-06

Courtside now uses a consistent forest-green, warm-white and lime visual system
with larger readable text, shared control sizes, restrained borders and consistent
spacing. The shared visual tokens and responsive rules live in
`web/src/refinement.css`.

## Changes

- Simplified main navigation; release checks are in the secondary workspace section.
- Academy workspace selection, team management and sign-out share the main header.
- Live Court gives the camera preview priority and groups camera selection,
  permission, junior fields and the start/stop action in one setup panel.
- Disabled live actions explain their prerequisites. Idle telemetry displays
  unavailable values instead of implying that measurements already exist.
- Revised overview, session cards, reports, progress, notes, settings and account
  forms use the same typography and visual hierarchy.
- Release checks have loading, error and retry states; technical training details
  are available in an expandable section.
- Phone navigation traps focus, closes on Escape, restores focus and keeps hidden
  navigation and background controls inert. Reduced motion preferences are honored.

## Verification

- Frontend suite: **26 passing tests** across four files.
- TypeScript checking and Vite production build: **passed**.
- Browser checks covered **320px and 390px phone layouts, 768px tablet layout,
  and the normal desktop viewport**.
- All main phone pages fit without horizontal document overflow after the header
  and tab adjustments.
- Checked session search, backhand filtering, report navigation, upload dialog
  opening and Escape dismissal against the built app.
- No browser console errors during the final production-build check.
- New regression checks cover mobile focus behavior, release-check recovery,
  incomplete junior permission, academy workspace switching, team actions,
  sign-in and sign-out. Account responses and camera hardware are mocked in tests.

This verifies the frontend changes. It does not establish tennis model accuracy,
backend academy security or physical-camera field performance.

Previews: `test-results/frontend-desktop.jpg`,
`test-results/frontend-mobile.jpg`, `test-results/frontend-overview.jpg`,
and `test-results/frontend-report.jpg`.

## Mobile follow-up

- Phone headers give the workspace selector a separate full-width row, with
  readable page names and 44px navigation and account controls.
- Mobile form fields use 16px text, and the viewport and layouts respect safe
  area insets. Filters stack on the smallest phones; library list rows place
  status below the session title.
- Live preview and setup stack below 820px. Phone reports keep the bounded shot
  picker before the selected shot, show all shot filters, and prevent status
  badges from overlapping titles.
- Charts adapt their plotting width while preserving readable labels, all data
  points and accessible descriptions. A resize regression test covers narrow
  layouts and empty-data transitions.
- Dialogs fit the dynamic viewport and keep the close control visible while
  scrolling. Navigation scrolls on short landscape screens and dims the inert
  background at every mobile breakpoint.
- Verified the production build at 320px, 390px and 540px phone widths, 768px
  tablet width, 844×390 landscape and the normal desktop viewport. All main
  pages passed the 320px horizontal-overflow check. Checked session list mode,
  report filtering, chart labels and upload-dialog scrolling; no console errors.

Updated phone preview: `test-results/frontend-mobile-refined.jpg`.
These browser viewport checks do not replace a physical iOS/Android device test.
