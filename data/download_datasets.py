"""Stage versioned CC BY tennis datasets without changing training consent checks."""

import argparse
import hashlib
import json
import shutil
import stat
import time
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REGISTRY = Path(__file__).with_name("datasets.json")
CHUNK_SIZE = 1024 * 1024
HTTP_HEADERS = {"User-Agent": "CourtsideDatasetDownloader/0.1", "Accept": "application/vnd.mendeley-public-dataset.1+json"}


class DownloadIntegrityError(ValueError):
    """A temporary download cannot be published because its bytes are invalid."""


def fetch_json(url: str):
    with urlopen(Request(url, headers=HTTP_HEADERS), timeout=30) as response:
        return json.load(response)


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_registry(path: Path = REGISTRY) -> list[dict]:
    datasets = json.loads(path.read_text(encoding="utf-8"))["datasets"]
    for dataset in datasets:
        if dataset["license"] != "CC BY 4.0" or dataset["training_ready"] is not False:
            raise ValueError("Only staged CC BY datasets are supported")
        safe_member(dataset["id"])
    return datasets


def safe_member(name: str) -> Path:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or PureWindowsPath(normalized).drive or ".." in path.parts or not path.parts:
        raise ValueError(f"Unsafe archive path: {name}")
    for part in path.parts:
        if ":" in part or part.rstrip(". ") != part or PureWindowsPath(part).is_reserved():
            raise ValueError(f"Unsafe archive path: {name}")
    return Path(*path.parts)


def require_space(root: Path, dataset: dict, mode: str = "auto") -> None:
    archive = root / dataset["id"] / "archive.zip"
    partial = archive.with_suffix(".zip.part")
    existing = archive.stat().st_size if archive.is_file() else partial.stat().st_size if partial.is_file() else 0
    required = max(0, dataset["archive_size_bytes"] - existing) + dataset["unpacked_size_bytes"] + 100 * CHUNK_SIZE
    if mode == "files":
        required = dataset["unpacked_size_bytes"] + 100 * CHUNK_SIZE
    free = shutil.disk_usage(root).free
    if free < required:
        raise ValueError(f"Insufficient space at {root}: need {required / 1024**3:.2f} GiB; free {free / 1024**3:.2f} GiB")


def download_archive(dataset: dict, target: Path, report: bool = True) -> None:
    if target.is_file():
        if target.stat().st_size != dataset["archive_size_bytes"] or file_sha256(target) != dataset["archive_sha256"]:
            raise ValueError(f"Existing archive failed verification: {target}")
        if report:
            print(f"Verified existing archive: {dataset['id']}", flush=True)
        return
    partial = target.with_name(target.name + ".part")
    downloaded = partial.stat().st_size if partial.is_file() else 0
    expected = dataset["archive_size_bytes"]
    if downloaded > expected or (downloaded == expected and file_sha256(partial) != dataset["archive_sha256"]):
        partial.unlink()
        downloaded = 0
    if downloaded < expected:
        headers = {"User-Agent": HTTP_HEADERS["User-Agent"], "Accept": "application/octet-stream"}
        if downloaded:
            headers["Range"] = f"bytes={downloaded}-"
        request = Request(dataset["archive_url"], headers=headers)
        with urlopen(request, timeout=60) as response:
            resumed = response.status == 206 and downloaded > 0
            if resumed and not response.headers.get("Content-Range", "").startswith(f"bytes {downloaded}-"):
                raise ValueError("Server returned an unexpected resume range")
            if not resumed:
                downloaded = 0
            last_progress = time.monotonic()
            with partial.open("ab" if resumed else "wb") as output:
                while chunk := response.read(CHUNK_SIZE):
                    output.write(chunk)
                    downloaded += len(chunk)
                    if downloaded > expected:
                        raise DownloadIntegrityError("Download is larger than the pinned archive size")
                    if report and time.monotonic() - last_progress >= 10:
                        print(f"{dataset['id']}: {downloaded / expected:.1%} downloaded", flush=True)
                        last_progress = time.monotonic()
    if partial.stat().st_size != expected or file_sha256(partial) != dataset["archive_sha256"]:
        partial.unlink()
        raise DownloadIntegrityError(f"Download failed size or SHA256 verification: {partial}")
    partial.replace(target)
    if report:
        print(f"Publisher SHA256 verified: {dataset['id']}", flush=True)


def publisher_file_index(dataset: dict) -> list[dict]:
    base = f"https://data.mendeley.com/public-api/datasets/{dataset['provider_id']}"
    folders = fetch_json(f"{base}/folders/{dataset['version']}")
    by_id = {folder["id"]: folder for folder in folders}

    def folder_path(folder_id, seen=None):
        if folder_id == "root":
            return Path()
        seen = set() if seen is None else seen
        if folder_id in seen or folder_id not in by_id:
            raise ValueError("Invalid publisher folder hierarchy")
        seen.add(folder_id)
        folder = by_id[folder_id]
        return folder_path(folder.get("parent_id", "root"), seen) / safe_member(folder["name"])

    records = []
    seen_paths = set()
    for folder_id in ["root", *by_id]:
        start = 0
        while True:
            files = fetch_json(f"{base}/files?folder_id={folder_id}&version={dataset['version']}&$start={start}&$limit=1000")
            for file in files:
                relative = folder_path(folder_id) / safe_member(file["filename"])
                key = relative.as_posix().casefold()
                if key in seen_paths:
                    raise ValueError("Duplicate publisher file path")
                seen_paths.add(key)
                details = file["content_details"]
                digest = details["sha256_hash"]
                if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                    raise ValueError("Publisher file is missing a valid SHA256")
                records.append({"path": relative.as_posix(), "size_bytes": details["size"], "sha256": digest, "url": details["download_url"]})
            if len(files) < 1000:
                break
            start += len(files)
    if not records:
        raise ValueError("Publisher file inventory is empty")
    return records


def download_publisher_files(dataset: dict, target: Path) -> None:
    records = publisher_file_index(dataset)
    contents = (target / "contents").resolve()
    contents.mkdir(exist_ok=True)
    if shutil.disk_usage(contents).free < sum(record["size_bytes"] for record in records) + 100 * CHUNK_SIZE:
        raise ValueError("Insufficient free space for publisher files")
    (target / "source_files.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    # Create shared parents before concurrent transfers resolve their destinations.
    for record in records:
        parent = (contents / safe_member(record["path"])).parent.resolve()
        if not parent.is_relative_to(contents):
            raise ValueError("Publisher folder escapes the dataset directory")
        parent.mkdir(parents=True, exist_ok=True)

    def download(record):
        path = (contents / safe_member(record["path"])).resolve()
        if not path.is_relative_to(contents):
            raise ValueError("Publisher path escapes the dataset directory")
        path.parent.mkdir(parents=True, exist_ok=True)
        expected = {"id": record["path"], "archive_url": record["url"], "archive_size_bytes": record["size_bytes"], "archive_sha256": record["sha256"]}
        for attempt in range(3):
            try:
                download_archive(expected, path, report=False)
                return
            except (OSError, DownloadIntegrityError):
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)

    print(f"{dataset['id']}: downloading {len(records)} publisher files with SHA256 verification", flush=True)
    last_progress = time.monotonic()
    failures = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        pending = {pool.submit(download, record): record for record in records}
        for completed, result in enumerate(as_completed(pending), 1):
            try:
                result.result()
            except (OSError, ValueError) as exc:
                failures.append(pending[result]["path"])
                print(f"Incomplete transfer: {pending[result]['path']}: {exc}", flush=True)
            if time.monotonic() - last_progress >= 10 or completed == len(records):
                print(f"{dataset['id']}: {completed - len(failures)}/{len(records)} files verified", flush=True)
                last_progress = time.monotonic()
    if failures:
        raise OSError(f"{len(failures)} transfers incomplete; rerun to retry them and reuse verified files")


def extract_archive(archive: Path, destination: Path) -> None:
    destination = destination.resolve()
    with zipfile.ZipFile(archive) as source:
        targets = []
        seen = set()
        total_bytes = 0
        for member in source.infolist():
            target = (destination / safe_member(member.filename)).resolve()
            if not target.is_relative_to(destination) or stat.S_ISLNK(member.external_attr >> 16):
                raise ValueError(f"Unsafe archive member: {member.filename}")
            # Windows paths are case-insensitive, even when tests run on Linux.
            key = str(target).casefold()
            if key in seen:
                raise ValueError(f"Duplicate archive path: {member.filename}")
            seen.add(key)
            total_bytes += member.file_size
            targets.append((member, target))
        destination.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(destination).free < total_bytes + 100 * CHUNK_SIZE:
            raise ValueError("Insufficient free space for archive extraction")
        for member, target in targets:
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(member) as input_file, target.open("wb") as output_file:
                    shutil.copyfileobj(input_file, output_file, CHUNK_SIZE)


def inventory_files(destination: Path) -> dict:
    files = []
    counts: Counter[str] = Counter()
    for path in sorted(destination.rglob("*")):
        if path.is_file():
            counts[path.suffix.lower()] += 1
            files.append({"path": path.relative_to(destination).as_posix(), "size_bytes": path.stat().st_size})
    return {"file_count": len(files), "file_types": dict(counts), "files": files}


def stage_dataset(dataset: dict, root: Path, mode: str = "auto") -> dict:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    require_space(root, dataset, mode)
    target = root / dataset["id"]
    target.mkdir(exist_ok=True)
    metadata = fetch_json(dataset["metadata_url"])
    if (
        metadata.get("id") != dataset["provider_id"]
        or metadata.get("version") != dataset["version"]
        or metadata.get("licence", {}).get("short_name") != dataset["license"]
    ):
        raise ValueError("Publisher identity, version or license differs from the pinned registry")
    (target / "publisher.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    attribution = (
        f"{dataset['title']} (version {dataset['version']})\n"
        f"Authors: {', '.join(dataset['authors'])}\n"
        f"DOI: https://doi.org/{dataset['doi']}\nSource: {dataset['source']}\n"
        f"License: {dataset['license']} - {dataset['license_url']}\n"
        "Original files are unmodified. Local inventory and review notes are separate.\n"
        "Staging does not attest participant consent, reviewed labels or production model eligibility.\n"
    )
    (target / "ATTRIBUTION.txt").write_text(attribution, encoding="utf-8")
    archive = target / "archive.zip"
    contents = target / "contents"
    archive_verified = False
    if mode != "files":
        try:
            download_archive(dataset, archive)
            extract_archive(archive, contents)
            archive_verified = True
        except HTTPError as exc:
            if mode != "auto" or exc.code not in {403, 404}:
                raise
            print(f"{dataset['id']}: cached ZIP unavailable; using official individual files", flush=True)
    if not archive_verified:
        download_publisher_files(dataset, target)
    inventory = {
        "dataset_id": dataset["id"],
        "source": dataset["source"],
        "doi": dataset["doi"],
        "license": dataset["license"],
        "archive_sha256": dataset["archive_sha256"],
        "archive_verified": archive_verified,
        "verification": "publisher-archive-sha256" if archive_verified else "publisher-file-sha256",
        "files_verified": True,
        "training_ready": False,
        "missing_for_current_trainer": dataset["missing_for_current_trainer"],
        **inventory_files(contents),
    }
    counts = inventory["file_types"]
    for suffix, expected_count in dataset.get("expected_files", {}).items():
        actual_count = counts.get(".jpg", 0) + counts.get(".jpeg", 0) if suffix == ".jpg_or_jpeg" else counts.get(suffix, 0)
        if actual_count != expected_count:
            raise ValueError(f"Unexpected {suffix} file count: expected {expected_count}, found {actual_count}")
    (target / "inventory.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    print(f"Staged {inventory['file_count']} files at {contents}", flush=True)
    return inventory


def main() -> None:
    datasets = load_registry()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).parent / "raw/external")
    parser.add_argument("--dataset", choices=["all", *[dataset["id"] for dataset in datasets]], default="all")
    parser.add_argument("--mode", choices=["auto", "archive", "files"], default="auto")
    args = parser.parse_args()
    try:
        locator_path = REGISTRY.with_name("local_datasets.json")
        locations = json.loads(locator_path.read_text(encoding="utf-8")) if locator_path.exists() else {}
        for dataset in datasets:
            if args.dataset in {"all", dataset["id"]}:
                inventory = stage_dataset(dataset, args.root, args.mode)
                location = args.root.resolve() / dataset["id"]
                locations[dataset["id"]] = {"contents": str(location / "contents"), "inventory": str(location / "inventory.json"), "training_ready": inventory["training_ready"]}
                locator_path.write_text(json.dumps(locations, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Dataset staging failed: {exc}\n")


if __name__ == "__main__":
    main()
