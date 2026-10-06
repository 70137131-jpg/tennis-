# Data handling

Never commit videos, pose exports, personal labels or model weights. `.gitignore`
excludes storage, models, `data/raw`, `data/labels`, analysis outputs and common
video/weight formats. Keep consented originals in `data/raw` or a private external
folder; label manifests and annotations in `data/labels`.

Use pseudonymous identities consistently across sessions. Split by both sessions
and every recorded player. A recording containing a train player cannot enter
validation/test even when the labeled shot belongs to their partner. Keep the
held-out test set frozen and separate from validation used for checkpoint selection.

Record the original SHA256, pose export SHA256, camera setup, label review,
processing consent and separate training consent. The app's normal uploads never
opt into training. A training manifest must attest consent for all recorded people
and verify the original file hash. Guardian consent and assent are required when
minors appear. The manifest checks evidence fields; legal consent is a human record.

Start with a few hundred reviewed shots per class, multiple players and independent
sessions. Use a local annotation tool of your choice to mark start/contact/end,
type and player identity. Hand-correct small pose/ball/court subsets for evaluation.
No third-party training data is bundled or downloaded. See `data/README.md` and
`docs/training.md`.
