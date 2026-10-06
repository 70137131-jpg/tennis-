# Dependency and artifact audit — 2026-10-05

Direct dependencies are recorded below. Installed first-party package metadata
and bundled LICENSE/OFL files were inspected; selected official upstream license
sources were also checked. `requirements.lock` and `package-lock.json` identify
the verified dependency set. New training code uses NumPy, with no ML framework
added. `docs/dependency_licenses.json` contains the clean Python environment's
metadata inventory; missing metadata is not assumed to grant rights.

| Component | Source/license | Use / release considerations |
|---|---|---|
| FastAPI, Pydantic | MIT package metadata | API and validation; retain notices |
| Uvicorn | BSD-3-Clause package metadata | ASGI transport |
| python-multipart | Apache-2.0 package metadata | Upload parsing |
| websockets | [BSD-3-Clause upstream](https://github.com/python-websockets/websockets/blob/main/LICENSE) | Live WebSocket transport |
| NumPy | BSD-3-Clause package metadata | Metrics, tracking and baseline training |
| OpenCV contrib Python | [Apache-2.0 OpenCV](https://opencv.org/license/) | Video/geometry; wheel may include separately licensed binary components |
| PyYAML | MIT package metadata | Versioned config |
| MediaPipe SDK | [Apache-2.0 upstream](https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE) | General pose inference; SDK license does not alone settle downloaded task/model terms |
| imageio-ffmpeg wrapper | BSD-2-Clause package metadata | Finds a local FFmpeg executable; audit the actual binary separately |
| FFmpeg with libx264 | [Official FFmpeg licensing](https://www.ffmpeg.org/legal.html) | Current H.264 renderer invokes this binary as a process. GPL components such as libx264 change binary licensing; distributing a commercial package/image requires a specific compliance review. This baseline does not claim permissive licensing for every binary. |
| React, React DOM, lucide-react | MIT / ISC package LICENSE metadata | UI and icons |
| Vite, TypeScript, React Vite plugin | MIT / Apache-2.0 package metadata | Frontend build tooling |
| Vitest | [MIT upstream](https://github.com/vitest-dev/vitest/blob/main/LICENSE) | Frontend tests only; updated to remove a reported advisory |
| Testing Library React/user-event, jsdom | [MIT upstream](https://github.com/testing-library/react-testing-library/blob/main/LICENSE) / package metadata | Component tests only |
| pytest, pytest-cov, coverage, httpx, Ruff, mypy, types-PyYAML | MIT/BSD/Apache-2.0 package metadata | Development/QA only; inspect inventory for exact versions |
| DM Sans, Plus Jakarta Sans | SIL Open Font License, included beside fonts | Locally hosted fonts; retain bundled OFL files |

No AGPL detector, Ultralytics YOLO package or third-party tennis training set is
part of the implementation. Dataset approval and general code licenses are
distinct from task-weight, font, binary and original-image rights. Unresolved
items remain explicit commercial release gates.
