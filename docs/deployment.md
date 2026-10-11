# Local and live deployment

The verified installation target is Windows with Python 3.11 and Node 22. A clean
environment using `requirements.lock` was installed and tested here. See README
for setup. Sign-in is required by default, and each account sees only its own
sessions. The app opens on **Sessions**; live camera analysis and uploads remain
available after sign-in.

## Start on this machine

```powershell
.qa-venv\Scripts\courtside.exe doctor
.qa-venv\Scripts\courtside.exe serve
```

Open `http://127.0.0.1:8000/#sessions` and create the first account on localhost.
Alternatively, configure [Google sign-in](google-signin.md) and use the exact
configured site address. After sign-in, choose a camera, attest processing permission,
click Start live feed and grant the browser's camera permission. Audio capture is
disabled. Optional spoken tips use browser speech synthesis. Stop or navigating
away closes the camera and live connection. Camera frames are processed in memory
and never written to disk or used for training.

The live socket authenticates in its initial message, so tokens do not appear in
URLs. There is one active live connection per workspace. Each client waits for its
frame result before sending another, preventing a backlog. Slow inference lowers
capture resolution; pose history resets when its coordinate system changes. A
stalled connection closes the camera and shows a reconnect message.

Ratings are percentages of confidently measured, shot-applicable metrics inside
configured ranges. These are experimental 2D proxies, not validated tennis skill
scores. Preview experimental coaching is explicit and can be disabled. Offline
reports continue to suppress real tips until coach approval. Live suggestions
arrive after the approximately 1.5-second follow-through window, plus compute and
transport latency. Hardware/tennis performance remains unvalidated.

## Phone access

Browser camera capture needs a secure context. `localhost` works on this machine;
plain `http://192.168...` on a phone generally cannot access its camera. Use a trusted
HTTPS endpoint/reverse proxy on your private network. See the [camera API's secure
context requirements](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia).
Do not bypass certificate warnings or expose the service without authentication.

For a public host, use personal account mode, an HTTPS reverse proxy, and
Google OAuth credentials as described in [Google sign-in](google-signin.md).
Run the Python server on loopback; expose only the HTTPS proxy. Do not expose
port 8000 directly to the internet.

Configure the reverse proxy for WebSocket Upgrade, long-lived connections and the
desired upload limit. Use HTTPS/WSS for any camera feed crossing a network. IP/RTSP
camera ingestion is not currently implemented; a browser-exposed/USB camera works.

## Docker

`Dockerfile` builds the React app and runs one non-root Python API/worker. Compose
persists storage and mounts downloaded models read-only. Compose binds the host
port to localhost and uses personal sign-in. Download the model on the host first.

```powershell
python data\download_model.py
docker compose config --quiet
docker compose up --build -d
```

`/api/health` is liveness; `/api/ready` verifies local prerequisites, including
initial account setup. A Docker image build has not been verified on this host.
The repository's Windows and Linux CI runs build and test the source.

## Persistence and release gates

Use one API process/embedded worker per storage root; multiple processes can
requeue each other's jobs. Stop the service before copying the complete storage
directory, including `.signing_key` and SQLite files. Protect backup access and
test restore into a separate directory before relying on it. Normal uploads may
contain minors' data; configure retention in Settings and test deletion on a
disposable session. Never publish the storage/model directories as static assets.

Public/commercial release additionally requires held-out end-to-end tennis
benchmarks, coach validation, live target-device/phone trials, academy pilot,
weight/codec distribution review and target-country privacy/legal review. No cloud
provider, public hosting or paid service has been configured.
