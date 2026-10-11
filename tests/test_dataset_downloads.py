import hashlib
import io
import json
import stat
import zipfile
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from data.download_datasets import (
    download_archive,
    extract_archive,
    load_registry,
    publisher_file_index,
    stage_dataset,
)


@pytest.fixture(autouse=True)
def sufficient_disk_space(monkeypatch):
    monkeypatch.setattr("data.download_datasets.shutil.disk_usage", lambda path: SimpleNamespace(free=10 * 1024**3))


def dataset_fixture(content):
    return {
        "id": "fixture",
        "provider_id": "example",
        "version": 1,
        "title": "Software test fixture",
        "doi": "test-doi",
        "source": "https://example.org/dataset",
        "metadata_url": "https://example.org/metadata",
        "archive_url": "https://example.org/archive.zip",
        "archive_size_bytes": len(content),
        "unpacked_size_bytes": 100,
        "archive_sha256": hashlib.sha256(content).hexdigest(),
        "license": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "authors": ["Test author"],
        "training_ready": False,
        "missing_for_current_trainer": ["reviewed labels"],
    }


class Response(io.BytesIO):
    status = 200
    headers = {}


def test_staging_records_verified_provenance_without_training_consent(tmp_path):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as source:
        source.writestr("annotations/actions.json", "{}")
    content = archive.getvalue()
    dataset = dataset_fixture(content)
    metadata = json.dumps({"id": "example", "version": 1, "licence": {"short_name": "CC BY 4.0"}}).encode()
    with patch("data.download_datasets.urlopen", side_effect=[Response(metadata), Response(content)]):
        inventory = stage_dataset(dataset, tmp_path)
    assert inventory["archive_verified"] and inventory["file_types"] == {".json": 1}
    assert inventory["training_ready"] is False and "consent" not in inventory
    assert json.loads((tmp_path / "fixture/inventory.json").read_text()) == inventory
    assert "Test author" in (tmp_path / "fixture/ATTRIBUTION.txt").read_text()


def test_download_rejects_corruption_before_publishing_archive(tmp_path):
    dataset = dataset_fixture(b"expected")
    with patch("data.download_datasets.urlopen", return_value=Response(b"tampered")):
        with pytest.raises(ValueError, match="SHA256"):
            download_archive(dataset, tmp_path / "archive.zip")
    assert not (tmp_path / "archive.zip").exists()


def test_partial_download_resumes_at_verified_byte_offset(tmp_path):
    content = b"test archive bytes"
    partial = tmp_path / "archive.zip.part"
    partial.write_bytes(content[:5])
    response = Response(content[5:])
    response.status = 206
    response.headers = {"Content-Range": f"bytes 5-{len(content) - 1}/{len(content)}"}
    with patch("data.download_datasets.urlopen", return_value=response) as fetch:
        download_archive(dataset_fixture(content), tmp_path / "archive.zip")
    assert fetch.call_args.args[0].get_header("Range") == "bytes=5-"
    assert (tmp_path / "archive.zip").read_bytes() == content


def test_resume_restarts_when_server_ignores_range(tmp_path):
    content = b"complete archive"
    (tmp_path / "archive.zip.part").write_bytes(content[:3])
    with patch("data.download_datasets.urlopen", return_value=Response(content)):
        download_archive(dataset_fixture(content), tmp_path / "archive.zip")
    assert (tmp_path / "archive.zip").read_bytes() == content


def test_corrupt_completed_partial_is_refetched(tmp_path):
    content = b"expected"
    (tmp_path / "archive.zip.part").write_bytes(b"tampered")
    with patch("data.download_datasets.urlopen", return_value=Response(content)) as fetch:
        download_archive(dataset_fixture(content), tmp_path / "archive.zip")
    assert fetch.call_args.args[0].get_header("Range") is None
    assert (tmp_path / "archive.zip").read_bytes() == content


def test_unavailable_cached_archive_uses_verified_publisher_files(tmp_path):
    content = b"reviewed source file"
    dataset = dataset_fixture(b"archive")
    metadata = {"id": "example", "version": 1, "licence": {"short_name": "CC BY 4.0"}}
    records = [{"path": "annotations/source.json", "size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(), "url": "https://example.org/file"}]
    with (
        patch("data.download_datasets.fetch_json", return_value=metadata),
        patch("data.download_datasets.publisher_file_index", return_value=records),
        patch("data.download_datasets.urlopen", side_effect=[HTTPError("https://example.org/archive", 403, "Forbidden", None, None), Response(content)]),
    ):
        inventory = stage_dataset(dataset, tmp_path)
    assert not inventory["archive_verified"]
    assert inventory["files_verified"] and inventory["verification"] == "publisher-file-sha256"
    assert (tmp_path / "fixture/contents/annotations/source.json").read_bytes() == content


def test_publisher_file_index_preserves_folders_and_checksums():
    folders = [{"id": "images", "name": "images"}, {"id": "serve", "name": "serve", "parent_id": "images"}]
    file = {"filename": "S_001.jpeg", "content_details": {"size": 123, "sha256_hash": "a" * 64, "download_url": "https://example.org/file"}}
    with patch("data.download_datasets.fetch_json", side_effect=[folders, [], [], [file]]):
        records = publisher_file_index(dataset_fixture(b"archive"))
    assert records[0]["path"] == "images/serve/S_001.jpeg"
    assert records[0]["sha256"] == "a" * 64


def test_publisher_file_index_rejects_escape_paths():
    file = {"filename": "../escape.txt"}
    with patch("data.download_datasets.fetch_json", side_effect=[[], [file]]):
        with pytest.raises(ValueError, match="Unsafe archive path"):
            publisher_file_index(dataset_fixture(b"archive"))


def test_failed_publisher_file_never_marks_dataset_complete(tmp_path):
    dataset = dataset_fixture(b"archive")
    metadata = {"id": "example", "version": 1, "licence": {"short_name": "CC BY 4.0"}}
    records = [{"path": "source.json", "size_bytes": 8, "sha256": hashlib.sha256(b"expected").hexdigest(), "url": "https://example.org/file"}]
    with (
        patch("data.download_datasets.fetch_json", return_value=metadata),
        patch("data.download_datasets.publisher_file_index", return_value=records),
        patch("data.download_datasets.urlopen", return_value=Response(b"tampered")),
    ):
        with pytest.raises(OSError, match="1 transfers incomplete"):
            stage_dataset(dataset, tmp_path, mode="files")
    assert not (tmp_path / "fixture/inventory.json").exists()


def test_staging_rejects_unexpected_dataset_file_counts(tmp_path):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as source:
        source.writestr("one.json", "{}")
    dataset = dataset_fixture(archive.getvalue())
    dataset["expected_files"] = {".json": 2}
    metadata = {"id": "example", "version": 1, "licence": {"short_name": "CC BY 4.0"}}
    with (
        patch("data.download_datasets.fetch_json", return_value=metadata),
        patch("data.download_datasets.urlopen", return_value=Response(archive.getvalue())),
    ):
        with pytest.raises(ValueError, match="file count"):
            stage_dataset(dataset, tmp_path)
    assert not (tmp_path / "fixture/inventory.json").exists()


@pytest.mark.parametrize("name", ["../escape.txt", "C:/escape.txt", "..\\escape.txt", "/escape.txt", "file:stream", "NUL.txt"])
def test_extraction_rejects_unsafe_paths_before_writing_files(tmp_path, name):
    archive = tmp_path / "archive.zip"
    with zipfile.ZipFile(archive, "w") as source:
        source.writestr("safe.txt", "safe")
        source.writestr(name, "unsafe")
    with pytest.raises(ValueError, match="Unsafe archive"):
        extract_archive(archive, tmp_path / "contents")
    assert not (tmp_path / "contents/safe.txt").exists()


def test_extraction_rejects_symlinks(tmp_path):
    archive = tmp_path / "archive.zip"
    with zipfile.ZipFile(archive, "w") as source:
        member = zipfile.ZipInfo("link")
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        source.writestr(member, "../target")
    with pytest.raises(ValueError, match="Unsafe archive member"):
        extract_archive(archive, tmp_path / "contents")


def test_extraction_rejects_case_collisions_on_every_platform(tmp_path):
    archive = tmp_path / "archive.zip"
    with zipfile.ZipFile(archive, "w") as source:
        source.writestr("Serve.json", "first")
        source.writestr("serve.json", "second")
    with pytest.raises(ValueError, match="Duplicate archive path"):
        extract_archive(archive, tmp_path / "contents")


def test_staging_rejects_license_changes(tmp_path):
    metadata = json.dumps({"id": "example", "version": 1, "licence": {"short_name": "CC BY-NC 4.0"}}).encode()
    with patch("data.download_datasets.urlopen", return_value=Response(metadata)):
        with pytest.raises(ValueError, match="license differs"):
            stage_dataset(dataset_fixture(b"archive"), tmp_path)
    assert not (tmp_path / "fixture/archive.zip").exists()


def test_staging_checks_disk_space_before_network_or_download(tmp_path, monkeypatch):
    monkeypatch.setattr("data.download_datasets.shutil.disk_usage", lambda path: SimpleNamespace(free=0))
    with patch("data.download_datasets.urlopen") as fetch:
        with pytest.raises(ValueError, match="Insufficient space"):
            stage_dataset(dataset_fixture(b"archive"), tmp_path)
    fetch.assert_not_called()


def test_registry_only_enables_cc_by_datasets():
    datasets = load_registry()
    assert len(datasets) == 2
    assert all(dataset["license"] == "CC BY 4.0" and not dataset["training_ready"] for dataset in datasets)
