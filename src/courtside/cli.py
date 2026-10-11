import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(prog="courtside", description="Private, local tennis video analysis")
    parser.add_argument("--version", action="version", version="courtside 0.1.0")
    sub = parser.add_subparsers(dest="command", required=True)
    analysis = sub.add_parser("analyze", help="Analyze a recorded MP4 or MOV")
    analysis.add_argument("video", type=Path)
    analysis.add_argument("--out", type=Path, default=Path("out"))
    analysis.add_argument("--handedness", choices=["left", "right"], default="right")
    analysis.add_argument("--backhand-style", choices=["one-handed", "two-handed"], default="two-handed")
    analysis.add_argument("--court", type=Path, help="JSON containing four normalized court corners")
    analysis.add_argument("--no-blur", action="store_true")
    serve = sub.add_parser("serve", help="Run the web app, API and local job worker")
    serve.add_argument("--host", default=os.environ.get("COURTSIDE_HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("COURTSIDE_PORT", "8000")))
    sub.add_parser("cleanup", help="Apply configured data-retention policy")
    sub.add_parser("doctor", help="Check local installation and release prerequisites")
    sub.add_parser("release-check", help="Check training manifests and reviewed release evidence")
    backup = sub.add_parser("backup", help="Create a verified backup while the service is stopped")
    backup.add_argument("--storage", type=Path, default=Path(os.environ.get("COURTSIDE_STORAGE", "storage")))
    backup.add_argument("--out", type=Path, required=True)
    restore = sub.add_parser("restore", help="Restore a backup into a new or empty directory")
    restore.add_argument("backup", type=Path)
    restore.add_argument("--storage", type=Path, required=True)
    training = sub.add_parser("train", help="Train a baseline on consented, reviewed shot labels")
    training.add_argument("--train", type=Path, required=True)
    training.add_argument("--validation", type=Path, required=True)
    training.add_argument("--test", type=Path, required=True)
    training.add_argument("--out", type=Path, default=Path("models/shot-baseline"))
    promotion = sub.add_parser("promote", help="Promote a classifier only after held-out targets pass")
    promotion.add_argument("model", type=Path)
    promotion.add_argument("--out", type=Path, default=Path("models/shot-classifier.json"))
    stream = sub.add_parser("stream", help="Experimental simulated-live analysis with adaptive workload")
    stream.add_argument("video", type=Path)
    stream.add_argument("--out", type=Path, default=Path("out/stream"))
    stream.add_argument("--window-seconds", type=float, default=6.0)
    stream.add_argument("--budget-seconds", type=float, default=10.0)
    args = parser.parse_args()
    if args.command == "analyze":
        from courtside.pipeline import analyze

        options = {
            "handedness": args.handedness,
            "backhand_style": args.backhand_style,
            "blur_faces": not args.no_blur,
        }
        if args.court:
            options["court_corners"] = json.loads(args.court.read_text())
        try:
            report = analyze(
                args.video,
                args.out,
                options,
                lambda percent, stage: print(f"\r{percent:3d}% {stage:36s}", end="", flush=True),
            )
            print(f"\n{len(report.shots)} candidates → {args.out.resolve() / 'report.json'}")
        except (ValueError, RuntimeError) as exc:
            parser.exit(1, f"\n{exc}\n")
    elif args.command == "serve":
        from api.auth_mode import configured_mode

        mode = configured_mode()
        if os.environ.get("COURTSIDE_ENV") == "production" and args.host not in {
            "127.0.0.1", "localhost", "::1"
        }:
            parser.exit(1, "Production must bind to loopback behind a trusted HTTPS reverse proxy.\n")
        if (
            args.host not in {"127.0.0.1", "localhost", "::1"}
            and len(os.environ.get("COURTSIDE_TOKEN", "")) < 24
            and mode == "local"
        ):
            parser.exit(1, "Phone/remote access requires COURTSIDE_TOKEN with at least 24 characters.\n")
        import uvicorn

        uvicorn.run("api.main:app", host=args.host, port=args.port, ws_max_size=1048576, ws_max_queue=1, access_log=False)
    elif args.command == "stream":
        from courtside.stream import simulate

        try:
            simulate(args.video, args.out, args.window_seconds, args.budget_seconds)
        except (ValueError, RuntimeError) as exc:
            parser.exit(1, f"{exc}\n")
    elif args.command in {"train", "promote"}:
        from courtside.pipeline import ROOT
        from courtside.training import promote, train

        try:
            if args.command == "train":
                model = train(
                    args.train, args.validation, args.test, args.out, ROOT / "configs/training.yaml"
                )
                print(
                    f"Held-out classifier macro F1: {model['held_out']['macro_f1']:.3f}. Candidate saved to {args.out}"
                )
            else:
                promote(args.model, args.out, ROOT / "configs/training.yaml")
                print(f"Promoted classifier: {args.out}")
        except (ValueError, KeyError, OSError) as exc:
            parser.exit(1, f"{exc}\n")
    elif args.command in {"backup", "restore"}:
        from courtside.operations import backup_storage, restore_storage

        try:
            result = backup_storage(args.storage, args.out) if args.command == "backup" else restore_storage(args.backup, args.storage)
            print(json.dumps(result, indent=2))
        except (ValueError, RuntimeError, OSError) as exc:
            parser.exit(1, f"{exc}\n")
    elif args.command == "release-check":
        from courtside.pipeline import ROOT
        from courtside.release import release_status

        status = release_status(ROOT)
        print(json.dumps(status, indent=2))
        if not status["release_ready"]:
            parser.exit(1)
    elif args.command == "doctor":
        from courtside.readiness import installation_status

        status = installation_status()
        print(json.dumps(status, indent=2))
        if not status["local_ready"]:
            parser.exit(1)
    else:
        from api.store import Store
        from worker.run import cleanup

        print(f"Deleted {cleanup(Store())} expired sessions")


if __name__ == "__main__":
    main()
