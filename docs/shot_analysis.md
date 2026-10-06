# Live shot identification and technique assessment

## Current behavior

Live Court finds candidate swings from hitting-wrist motion relative to the torso,
so whole-body movement and camera scale changes alone do not trigger a shot.
The baseline proposes forehand, backhand, serve, or volley. Anatomical shoulder
orientation supports players facing toward or away from the camera. Ambiguous
wrist/shoulder geometry remains `unknown`; an overhead swing away from the
baseline is also unknown when court calibration is available. Near-net position
and a compact swing suggest a volley. These are movement heuristics; no trained
tennis classifier or verified racket-contact detector is installed.

The latest-shot panel shows the tracked player, detection confidence, and the
observations behind the proposed type. Confidence is an engineering estimate,
not a measured accuracy rate. A ball candidate near the wrist adds supporting
evidence without establishing racket contact.

## What the technique assessment means

Preparation and finish measurements use frames before and after the candidate
contact respectively (approximately 0.5 seconds before and 0.8 seconds after).
Missing, stale, clipped, or occluded phases stay unmeasurable.
Applicable targets come from `configs/feedback_rules.yaml`, including age/level
adjustments:

- Forehand/backhand: preparation knee angle and finish wrist height.
- Serve: preparation knee angle and contact elbow extension.
- Volley/unknown: no overall score until applicable evidence and targets exist.

Each check reports its phase, measured value, range, and within/below/above-target
status. A percentage is produced only when all configured checks and at least
two checks are reliable. It is the fraction within the configured ranges, not a
rating of ball placement, power, spin, or match effectiveness. Live experimental
coaching must be enabled, or the rules must have coach approval. Disabling the
preview retains raw measurements and suppresses comparisons, scores, and tips.

## First camera trial

1. Run `npm run build`, then `courtside serve` in the activated Python environment.
2. Open `http://127.0.0.1:8000/#live`. Check handedness and level in Settings.
   The current handedness setting applies to both tracked players.
3. Use a fixed camera behind the baseline with the full body visible; complete
   processing consent, then start the live feed. Calibrate court corners to help
   distinguish net play from baseline strokes.
4. Try forehands, backhands, serves, volleys, and ordinary movement separately.
   Allow follow-through to finish before checking the latest-shot panel.
5. Compare proposed types with a human's observations. Review technique values
   with a qualified coach; the current target ranges are unvalidated hypotheses.

Frames are processed in memory and are not saved for training. Real classification
accuracy and technique agreement still require separately consented recordings,
manual shot/phase labels, and coach review. See `docs/training.md` for the existing
training and held-out promotion workflow. Synthetic regression tests verify
software behavior only.
