# PRD: AI Tennis Coach (working name: `courtside`)

> **Audience for this document:** Claude Code, acting as a senior ML/software engineer building this project with a solo developer (Ali).
> **How to use it:** Read the whole document first. Work phase by phase. Do not skip ahead to later phases until the acceptance criteria of the current phase pass. Ask the developer before making decisions marked **[DECISION NEEDED]**.

---

## 1. Summary

A computer-vision system that watches tennis sessions from a single fixed camera, detects and classifies each shot, measures the player's technique with pose estimation, and returns **rule-based coaching feedback** as an **annotated video with skeleton overlay** viewable in a **web app on a phone browser**.

The product is intended for **competitive juniors and tennis academies**, and may be sold to academies later. This affects licensing, privacy, and architecture decisions throughout.

## 2. Goals and Non-Goals

### Goals
1. Post-session analysis: upload a recorded session, get a per-shot report and annotated clips.
2. Support all shot types: serve, forehand, backhand, volley (forehand and backhand volleys may be grouped initially).
3. Support partner rallies and full singles matches from one fixed camera.
4. Rule-based, explainable feedback with every tip traceable to a measured metric and a threshold.
5. Run entirely on **free tiers and the developer's own hardware** (local NVIDIA GPU plus Google Colab).
6. Later phase: near real-time feedback between shots.
7. Keep the codebase commercially usable: avoid dependencies whose licenses block selling the product.

### Non-Goals (for now)
- No LLM-generated feedback. Feedback is rule-based only. (Keep the feedback module behind an interface so an LLM layer could be added later, but do not build it.)
- No native mobile app. Web app only.
- No multi-camera 3D reconstruction.
- No doubles support.
- No line-calling, scoring, or umpiring.
- No paid APIs or paid cloud services.

## 3. Users and Use Cases

| User | Need |
|---|---|
| Junior player | See what they did on each shot and get 1 to 3 clear tips |
| Coach | Review a session fast, see trends per player, show visual evidence to the player |
| Academy admin (later) | Manage players, sessions, and consent |

Primary flow (Phase 1 to 3):
1. Camera records a session (or the user uploads a video file).
2. Video is uploaded through the web app.
3. Backend processes it into shots, metrics, and annotated clips.
4. Player opens the report on their phone: session summary, list of shots, each shot with skeleton-overlay clip, metrics, and tips.

## 4. Camera and Capture Specification

Recommend and document this in `docs/camera_setup.md`. Starting recommendation:

- **Position:** behind the baseline, centered on the court's long axis, **elevated 3 to 5 m** (fence mount, tall tripod, or platform), tilted down about 15 to 25 degrees. This sees both players, shows the near player from behind, and gives a usable view of the far player and ball flight along the court.
- **Optional second angle (post-MVP experiment):** side-on elevated view for better racket-path and contact-point measurement.
- **Resolution and fps:** minimum 1080p at 60 fps. 4K at 30 or 60 fps is preferred if storage and compute allow, because the far-side player and the ball are small. Fixed exposure and fast shutter (about 1/500 s or faster) to limit motion blur. Lock focus.
- **Hardware options to document:** phone on a mount, action camera (GoPro class), cheap IP camera. Include power, storage, and mounting notes.
- **Court calibration:** detect the court's key points once per session (or per fixed-camera setup) and compute a homography so image positions map to court positions. Needed for ball landing, player position, and far/near player assignment.

**[DECISION NEEDED]** Which camera hardware the developer will actually use. Start by building against whatever footage they already have.

## 5. Functional Requirements

### 5.1 Ingestion
- FR-1: Accept video upload (mp4, mov) through the web app, with resumable or chunked upload if feasible on the free tier.
- FR-2: Validate resolution, fps, duration; reject or warn on unsupported input.
- FR-3: Store the original video and derived artifacts; link them to a session record.

### 5.2 Vision pipeline
- FR-4: **Court detection and calibration** (keypoints plus homography).
- FR-5: **Player detection and tracking** with stable IDs across the whole session; identify "near" and "far" player using court geometry.
- FR-6: **Pose estimation** per tracked player per frame (17 COCO keypoints minimum; a wholebody or hand model is optional later), with temporal smoothing.
- FR-7: **Ball detection and tracking** (small fast object; tracking-specific model or fine-tuned detector), with trajectory interpolation across missed frames.
- FR-8: **Shot segmentation:** find the start, contact, and end frame of each shot using a combination of ball trajectory changes (direction/velocity change near a player) and wrist/racket-arm velocity peaks.
- FR-9: **Shot classification:** serve, forehand, backhand, volley (and optionally overhead/smash). Use a temporal model over pose sequences (for example, a small GRU, TCN, or ST-GCN over keypoints) or a simple baseline first.
- FR-10: **Racket handling:** racket detection is optional. Start with wrist-based proxies. Add racket detection only if metrics demand it.

### 5.3 Metrics and rule-based feedback
- FR-11: Compute technique metrics per shot at key phases (see Section 7).
- FR-12: Feedback engine reads thresholds from a **versioned YAML config**, compares metrics, and emits tips ranked by severity. Max 3 tips per shot, max 5 per session summary.
- FR-13: Every tip must include: the metric name, the measured value, the target range, and a plain-language explanation. No tip without a measurement behind it.
- FR-14: Handle uncertainty. If keypoint confidence is low or the shot is occluded, **do not emit a tip**; mark the metric as "not measurable".

### 5.4 Rendering
- FR-15: Render an **annotated video clip per shot**: skeleton overlay, highlighted key joints for the failing metric, contact-frame marker, optional ball trail, and short text label. Also render a full-session annotated video.
- FR-16: Clips should be web-friendly (H.264 mp4, reasonable bitrate) and playable on mobile browsers.

### 5.5 Web app (phone-first)
- FR-17: Mobile-first responsive UI: upload, processing status, session report, shot list, shot detail with video, metrics, and tips.
- FR-18: Session history and a simple progress view (metric trends across sessions for the same player).
- FR-19: Basic accounts or a simple token-based access model. Keep it minimal in the MVP. **[DECISION NEEDED]**
- FR-20: Player and coach roles are a later addition (Phase 5).

### 5.6 Near real-time mode (Phase 4)
- FR-21: Process a live or near-live stream in short windows and return feedback for the latest shot within a target latency (see Section 10).
- FR-22: Degrade gracefully: if the system falls behind, skip frames or lower resolution rather than fail.

## 6. Data

### 6.1 Sources
Build a `data/README.md` that lists each dataset, how to download it, its license, and its intended use. **Verify every license yourself before use; do not rely on this table.** Because the product may be sold, flag any research-only or non-commercial license clearly and keep such data out of any model that ships, or use it only for evaluation.

| Need | Candidates to evaluate |
|---|---|
| General pose pretraining | COCO Keypoints (and COCO-WholeBody) |
| Tennis shot classification | THETIS (tennis shot video dataset), TenniSet, other published tennis action datasets |
| Ball tracking | TrackNet tennis datasets and similar published ball-tracking sets |
| Court keypoints | Published tennis court keypoint datasets, plus self-labeled frames |
| Own data | Developer's recorded videos (primary source for domain fit) |

**[DECISION NEEDED]** After the license audit, confirm which datasets are allowed for training a shipped model versus evaluation only.

### 6.2 Own data collection and labeling
- Record a variety of sessions: different players (including juniors), courts, lighting, and times of day.
- Label with an open-source tool (for example CVAT or Label Studio) running locally: shot boundaries and shot type per shot, ball position on sampled frames, court keypoints on a few frames per setup, and (small subset) pose corrections for validation.
- Target starting sizes (adjust with results): a few hundred labeled shots per class for classification fine-tuning, a few thousand ball-labeled frames for ball detector fine-tuning, and 20 to 50 labeled frames per camera setup for court keypoints.
- Keep a **held-out evaluation set that is never used for training**, split by session and by player to avoid leakage.

### 6.3 Data hygiene
- Raw video lives outside git. Use DVC, git-lfs, or plain scripted download paths. Document in `docs/data.md`.
- Every dataset and model artifact is versioned and referenced by ID in experiment logs.

## 7. Technique Metrics (initial rule set)

Metrics are computed from smoothed 2D keypoints (plus court homography where useful). All thresholds go in `configs/feedback_rules.yaml`, are **adjustable by age group and level**, and must be **validated by a qualified coach** before being shown to real players. Treat the numbers below as starting hypotheses, not facts.

| Shot | Phase | Candidate metrics |
|---|---|---|
| Serve | Preparation / trophy | Knee bend, front-arm height, racket-arm elbow angle, shoulder tilt |
| Serve | Contact | Contact height relative to full reach, arm extension, body position relative to baseline |
| Serve | Follow-through | Finish side and balance |
| Forehand | Preparation | Shoulder turn, early racket preparation timing |
| Forehand | Contact | Contact point in front of the body, elbow angle, knee bend, weight transfer proxy |
| Forehand | Follow-through | Finish height and direction |
| Backhand | Preparation / contact / follow-through | Same structure as forehand, with one-hand and two-hand variants **[DECISION NEEDED]** |
| Volley | Preparation | Short backswing, racket-side shoulder turn |
| Volley | Contact | Contact in front of the body, firm wrist proxy, split-step presence before the shot |
| All | General | Shot tempo, recovery step speed, court position at contact |

Implementation notes:
- Compute metrics at **named key frames** (preparation, contact, finish), not on every frame.
- Include per-metric confidence derived from keypoint scores.
- Left-handed players: detect handedness (from serve and dominant-arm movement) or let the user set it, and mirror rules accordingly.

## 8. Technology Choices

Pick open-source, permissively licensed components by default. **Licensing check required before adopting any model or library.**

- **Language and ML:** Python 3.11+, PyTorch, OpenCV, NumPy.
- **Pose:** prefer **RTMPose via MMPose** or **MediaPipe Pose** (Apache-2.0 style licenses). **Avoid depending on Ultralytics YOLO for the shipped product** unless the developer buys an enterprise license, because its AGPL-3.0 license has strong copyleft implications for a sold product. It is fine for quick local experiments if clearly marked as non-shipping.
- **Player detection and tracking:** a permissively licensed detector (for example RTMDet or similar) plus a tracker such as ByteTrack. Verify licenses.
- **Ball tracking:** evaluate TrackNet-style models (check license and weights) versus a fine-tuned small detector with temporal post-processing.
- **Shot classification:** start with a rule/heuristic or small sequence model on pose keypoints; upgrade if F1 is insufficient.
- **Backend API:** FastAPI.
- **Job processing:** a simple job queue with a worker process (for example a database-backed queue or RQ/Celery-lite). Keep it simple.
- **Frontend:** a mobile-first web app (React or Next.js, or SvelteKit). Plain, fast, accessible. **[DECISION NEEDED]** framework.
- **Video rendering:** OpenCV or FFmpeg for overlays and encoding.
- **Experiment tracking:** MLflow or Weights & Biases free tier, plus config-driven runs (Hydra or plain YAML).
- **Testing:** pytest, plus a small set of golden videos with expected outputs.
- **CI:** GitHub Actions free tier: lint (ruff), type check (mypy or pyright), unit tests.

## 9. Architecture

### 9.1 Free-tier MVP architecture (recommended)

```
 Phone / Browser (web app)
        |  upload video, view reports
        v
 Frontend host (free static/edge hosting)
        |
        v
 API (FastAPI) + metadata DB + object storage (free tiers)
        |  enqueue job
        v
 Job queue (DB-backed)
        |  worker pulls job
        v
 GPU worker (developer's local machine, or Colab for batch runs)
   - court calibration
   - detection + tracking
   - pose + ball
   - shot segmentation + classification
   - metrics + feedback rules
   - render annotated clips
        |  upload results
        v
 Object storage (clips, JSON report) -> web app displays
```

Reasoning: GPU inference is the expensive part and free cloud tiers rarely include GPUs. Running the **worker on the developer's own GPU** that pulls jobs from a hosted queue keeps the cost at zero while the API and UI stay online. A CPU-only hosted worker can handle short clips as a fallback.

**[DECISION NEEDED]** Which free providers to use for hosting, database, and object storage. Check current free-tier limits before committing (video storage and egress are the usual bottlenecks).

### 9.2 Later evolution
- Phase 4 (near real-time): an **on-court edge device** (a laptop with GPU or a Jetson-class device) processes the stream locally, and only results go to the cloud. Streaming raw video to a free cloud tier is not realistic.
- Phase 5 (multi-academy): move to paid cloud GPU workers, add multi-tenant accounts, and keep all processing code unchanged behind the same worker interface.

### 9.3 Core design rules
- The vision pipeline is a **standalone Python package** with a CLI (`courtside analyze video.mp4 --out out/`) so it works without the web app.
- Each stage has a clear input/output schema (Pydantic models) and writes intermediate artifacts to disk for debugging.
- The report is a **JSON document with a versioned schema**; the frontend only renders that JSON.
- The feedback engine is a pure function: `metrics + config -> tips`. Fully unit-testable.

## 10. Non-Functional Requirements

| Area | Requirement |
|---|---|
| Post-session speed | Initial target: a 10-minute 1080p session processed in under about 3x real time on the local GPU. Tune later. |
| Near-real-time latency (Phase 4) | Feedback for a shot within roughly 5 to 10 seconds of contact on the edge device. **[DECISION NEEDED]** confirm target after Phase 3 benchmarks. |
| Accuracy (initial targets, refine with data) | Shot classification macro-F1 of at least 0.85 on held-out own data; shot segmentation within about 0.2 s of labeled contact for most shots; ball detected in the large majority of in-flight frames after interpolation |
| Robustness | Handles changes in lighting, shadows, partial occlusion, and different courts without manual re-tuning beyond court calibration |
| Reproducibility | A fresh clone plus documented commands reproduces the pipeline results on sample data |
| Cost | Zero recurring cost in MVP |
| Accessibility and UX | Usable one-handed on a phone; clear contrast; no jargon-only tips |

## 11. Privacy, Consent, and Safety

Competitive juniors means **minors**. Treat this as a requirement, not an afterthought.

- Collect and store explicit **parental or guardian consent** (and player assent) before any session of a minor is processed in the product. Provide a consent record per player.
- Minimize retention: configurable retention period; deletion on request removes video, derived clips, and metrics.
- Do not use any player's video for model training without separate, explicit consent.
- Provide an option to **blur faces** or run in "local-only" mode where video never leaves the academy's machine.
- Secure storage and access control: signed URLs for video, no public buckets.
- Feedback tone and content must be age-appropriate and **never give medical or injury-diagnosis claims**. For safety-relevant observations (for example, a serve motion that may strain the shoulder), phrase as "talk to your coach" rather than as medical advice. Include a short disclaimer in the app.
- Obtain legal review before commercial launch. Data protection rules vary by country. **[DECISION NEEDED]** target launch countries.

## 12. Evaluation Plan

Create `eval/` with scripts that run on the held-out set and produce a markdown report:

- **Pose:** keypoint accuracy (PCK or OKS) on a small hand-corrected subset; temporal jitter measure.
- **Tracking:** ID switches per session; correct near/far assignment rate.
- **Ball:** detection precision and recall, trajectory continuity.
- **Shot segmentation:** contact-frame error distribution; missed and false shots.
- **Shot classification:** confusion matrix and per-class F1.
- **Feedback quality:** a **coach review study**: a coach rates a sample of tips as correct, incorrect, or unhelpful. Track agreement rate over time. This is the metric that matters for the product.
- **System:** processing time, memory, failure rate.

Every model or rule change is evaluated against the same held-out set and logged.

## 13. Maintenance Plan

- Version everything: code (git tags), models (registry or tagged artifacts), rule configs (`feedback_rules` version in every report), and report schema.
- Log per-session diagnostics (confidence summaries, failure flags) without storing extra personal data.
- Provide an in-app thumbs up/down on each tip and an optional coach correction. Store these as labeled feedback for the next rule/model iteration (subject to consent).
- Retraining cadence: re-run evaluation on each new batch of labeled data; promote a model only if it beats the current one on the held-out set without regressions on any class.
- Keep a `CHANGELOG.md` and a `docs/known_issues.md` (lighting failures, camera angles that break, and similar).

## 14. Roadmap and Phases

Each phase ends with a demo and its acceptance criteria. Do not start a phase until the previous one passes.

### Phase 0: Foundations
- Repo scaffold, tooling, CI, config system, CLI skeleton, sample data download scripts, `docs/` stubs.
- Dataset and license audit (`data/README.md`).
- Camera setup doc (`docs/camera_setup.md`).
- **Acceptance:** `courtside --help` works, CI green, license audit committed, developer has chosen the camera and sample footage.

### Phase 1: Single-player pose and shot segmentation (offline, CLI)
- Player detection, pose estimation with smoothing, skeleton overlay video.
- Shot segmentation (contact detection) using wrist velocity first, ball later.
- Shot classification baseline.
- **Acceptance:** on the developer's sample videos, the CLI outputs an annotated video and a JSON listing detected shots with types; classification meets a first-pass F1 target; evaluation script exists.

### Phase 2: Ball tracking, court calibration, and two-player matches
- Court keypoints and homography, ball tracking, near/far player assignment and tracking IDs.
- Improve shot segmentation with ball trajectory.
- **Acceptance:** works on a rally and on a full singles match clip; per-player shot lists; evaluation report on held-out data.

### Phase 3: Metrics, rule-based feedback, and per-shot annotated clips
- Implement metrics (Section 7) and the YAML rule engine with confidence handling.
- Render per-shot clips with failing-metric highlights.
- Coach review of the first rule set.
- **Acceptance:** report JSON with tips traceable to metrics; coach agreement measured on a sample; no tip emitted on low-confidence shots.

### Phase 4: Web app and job pipeline (MVP release)
- FastAPI backend, queue, worker, storage, mobile-first frontend, session history.
- **Acceptance:** a user can upload a session from a phone browser, see processing status, and view the full report and annotated clips, with the worker running on the developer's machine. Deployed using free tiers.

### Phase 5: Near real-time mode
- Windowed streaming pipeline on an edge device, latency benchmarks, graceful degradation.
- **Acceptance:** feedback for a shot returns within the agreed latency on target hardware in a live or simulated-live test.

### Phase 6: Academy readiness
- Accounts and roles (player, coach, admin), consent management, retention controls, coach dashboard, progress trends, pilot with one academy, pricing and cost model, legal review.
- **Acceptance:** pilot academy completes at least a few real sessions; feedback collected; go/no-go decision documented.

## 15. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Far-side player is small, so poor pose | Bad metrics for the far player | Higher resolution, crop-and-zoom second-pass pose on the tracked player box, mark low-confidence metrics as not measurable |
| Ball is tiny and blurred | Missed shots, weak segmentation | Fine-tune on own data, high fps and fast shutter, trajectory interpolation, fall back to wrist-velocity segmentation |
| Single 2D camera limits angles | Some metrics unreliable | Choose metrics robust to the camera angle, document unsupported metrics, evaluate a second angle later |
| Occlusion by net, fence, or other player | Missing keypoints | Temporal smoothing, confidence gating, no tips when uncertain |
| Licensing blocks commercialization | Rework later | Audit early (Phase 0), prefer Apache/MIT/BSD, avoid AGPL dependencies in the shipped path |
| Wrong or harmful coaching tips | Trust and safety issue for juniors | Coach-validated thresholds, tip traceability, age-appropriate config, disclaimers, thumbs up/down loop |
| Free-tier limits (storage, egress, compute) | MVP cannot scale | Short clips, aggressive video compression, local GPU worker, keep an exit path to paid tiers |
| Scope too large (all shots, matches, real time) | Project stalls | Strict phase gates; do the post-session pipeline first |
| Minors' data | Legal and ethical exposure | Section 11 requirements from day one |

## 16. Proposed Repository Structure

```
courtside/
  README.md
  PRD.md
  CHANGELOG.md
  pyproject.toml
  configs/
    pipeline.yaml
    feedback_rules.yaml
  src/courtside/
    cli.py
    io/              # video read/write, schemas
    court/           # court keypoints, homography
    detection/       # player + ball detection
    tracking/        # player + ball tracking
    pose/            # pose estimation + smoothing
    shots/           # segmentation, classification
    metrics/         # technique metrics
    feedback/        # rule engine (pure functions)
    render/          # overlays, clip export
    report/          # report schema + builder
  api/               # FastAPI app
  worker/            # job worker
  web/               # frontend
  eval/              # evaluation scripts + reports
  data/              # README, download scripts (no raw video in git)
  notebooks/         # Colab/experiment notebooks
  tests/
  docs/
    camera_setup.md
    data.md
    architecture.md
    known_issues.md
```

## 17. Working Agreement for Claude Code

1. **Start with Phase 0.** Before writing pipeline code, produce: the repo scaffold, the license audit, and a short written plan for Phase 1, then ask the developer to confirm the open **[DECISION NEEDED]** items that block Phase 1.
2. Work in **small, reviewable commits**. Each commit should run tests.
3. **Write tests first or alongside** for the feedback engine, metric functions, and schema code. Use synthetic keypoint sequences for metric tests.
4. Prefer **simple baselines before complex models**. Report baseline numbers before replacing a component.
5. Never hard-code thresholds in code; they belong in `configs/feedback_rules.yaml`.
6. Do not add dependencies without checking their license and recording it in `docs/licenses.md`.
7. Do not commit video, weights, or personal data. Add them to `.gitignore` and document download paths.
8. When uncertain about a fact (dataset license, model weights terms, free-tier limits), **verify it from the official source** and cite it in the docs rather than assuming.
9. After each phase, update `README.md`, `CHANGELOG.md`, and the evaluation report, and summarize results and remaining risks for the developer.

## 18. Open Decisions (summary)

- Camera hardware and final placement
- Which datasets are allowed in shipped models (after license audit)
- One-hand versus two-hand backhand handling
- Frontend framework
- Free-tier providers for hosting, database, and storage
- Account model for the MVP
- Near-real-time latency target
- Target launch countries and legal review
