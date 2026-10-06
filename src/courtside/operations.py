"""Single-process storage ownership and verified offline backup/restore."""

import hashlib
import json
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


class StorageLock:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.file = None

    def __enter__(self):
        self.root.mkdir(parents=True, exist_ok=True)
        self.file = (self.root / ".runtime.lock").open("a+b")
        self.file.seek(0)
        if not self.file.read(1):
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            self.file = None
            raise RuntimeError(
                "This storage is in use. Stop its server before maintenance or a second start."
            ) from exc
        return self

    def __exit__(self, *args):
        if self.file:
            if sys.platform == "win32":
                import msvcrt

                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
            self.file.close()
            self.file = None


def backup_storage(root: Path, destination: Path):
    root, destination = root.resolve(), destination.resolve()
    if destination.is_relative_to(root) or destination.exists():
        raise ValueError("Choose a new backup file outside the storage directory")
    if not root.is_dir():
        raise ValueError("Storage directory not found")
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest = {}
    with StorageLock(root), zipfile.ZipFile(destination, "x", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError("Backup refuses linked files or directories")
            if not path.is_file() or path.name == ".runtime.lock" or path.name.endswith(("-wal", "-shm")):
                continue
            relative = path.relative_to(root).as_posix()
            if path.suffix in {".db", ".sqlite", ".sqlite3"}:
                with tempfile.TemporaryDirectory() as temporary:
                    copy = Path(temporary) / "snapshot.db"
                    with sqlite3.connect(path) as source, sqlite3.connect(copy) as target:
                        source.backup(target)
                        if target.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                            raise ValueError("Database integrity check failed")
                    archive.write(copy, relative)
                    manifest[relative] = hashlib.sha256(copy.read_bytes()).hexdigest()
            else:
                with path.open("rb") as source:
                    manifest[relative] = hashlib.file_digest(source, "sha256").hexdigest()
                archive.write(path, relative)
        archive.writestr("backup-manifest.json", json.dumps({"schema": 1, "files": manifest}, sort_keys=True))
    return {"files": len(manifest), "backup": str(destination)}


def restore_storage(source: Path, target: Path):
    target = target.resolve()
    if target.exists() and any(target.iterdir()):
        raise ValueError("Restore requires a new or empty storage directory")
    with zipfile.ZipFile(source) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or len(names) > 100000:
            raise ValueError("Backup has duplicate paths or too many files")
        for info in archive.infolist():
            archive_path = PurePosixPath(info.filename)
            if (
                archive_path.is_absolute()
                or ".." in archive_path.parts
                or ":" in info.filename
                or "\\" in info.filename
                or info.is_dir()
                or (info.external_attr >> 16) & 0o170000 == 0o120000
            ):
                raise ValueError("Unsafe backup path")
        if sum(i.file_size for i in archive.infolist()) > 50 * 1024**3:
            raise ValueError("Backup exceeds the restore size limit")
        manifest = json.loads(archive.read("backup-manifest.json"))
        if manifest.get("schema") != 1 or set(manifest.get("files", {})) != set(names) - {
            "backup-manifest.json"
        }:
            raise ValueError("Backup manifest does not match the archive")
        for name, expected in manifest["files"].items():
            with archive.open(name) as data:
                digest = hashlib.sha256()
                for block in iter(lambda: data.read(1024 * 1024), b""):
                    digest.update(block)
                if digest.hexdigest() != expected:
                    raise ValueError("Backup checksum mismatch")
        target.mkdir(parents=True, exist_ok=True)
        for name in manifest["files"]:
            path = (target / name).resolve()
            if not path.is_relative_to(target):
                raise ValueError("Unsafe restore destination")
            path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as data, path.open("xb") as output:
                import shutil

                shutil.copyfileobj(data, output)
        # Restored sign-in cookies must not revive old credentials.
        for path in target.rglob("accounts.sqlite3"):
            with sqlite3.connect(path) as db:
                db.execute("DELETE FROM auth_sessions")
    return {"restored_files": len(manifest["files"]), "storage": str(target)}
