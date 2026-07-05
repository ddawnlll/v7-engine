"""Tests for SHA-256 batch checksum verification for data lake files."""

from __future__ import annotations

import hashlib
from pathlib import Path

from lib.data_lake.checksum import (
    ChecksumReport,
    compute_sha256,
    find_sidecar_files,
    generate_checksums,
    verify_checksums,
)


def test_compute_sha256(tmp_path: Path) -> None:
    """Known content produces a known SHA-256 hash."""
    content = b"hello world"
    fp = tmp_path / "test.txt"
    fp.write_bytes(content)

    expected = hashlib.sha256(content).hexdigest()
    actual = compute_sha256(fp)
    assert actual == expected


def test_verify_all_pass(tmp_path: Path) -> None:
    """When all hashes match, files_failed is empty."""
    files: list[Path] = []
    expected_hashes: dict[str, str] = {}
    for name in ("a.txt", "b.txt", "c.txt"):
        content = name.encode()
        fp = tmp_path / name
        fp.write_bytes(content)
        files.append(fp)
        expected_hashes[name] = hashlib.sha256(content).hexdigest()

    report = verify_checksums(files, expected_hashes)
    assert report.total_files == 3
    assert report.files_checked == 3
    assert report.files_passed == 3
    assert report.files_failed == []


def test_verify_some_fail(tmp_path: Path) -> None:
    """Mismatched hashes are correctly reported in files_failed."""
    fp1 = tmp_path / "good.txt"
    fp2 = tmp_path / "bad.txt"
    fp1.write_bytes(b"good content")
    fp2.write_bytes(b"bad content")

    expected = {
        "good.txt": hashlib.sha256(b"good content").hexdigest(),
        "bad.txt": hashlib.sha256(b"wrong expected").hexdigest(),
    }

    report = verify_checksums([fp1, fp2], expected)
    assert report.total_files == 2
    assert report.files_checked == 2
    assert report.files_passed == 1
    assert report.files_failed == [fp2]


def test_generate_and_verify(tmp_path: Path) -> None:
    """Round-trip: generate CHECKSUM then verify against it."""
    files: list[Path] = []
    for name in ("x.bin", "y.bin"):
        fp = tmp_path / name
        fp.write_bytes(name.encode())
        files.append(fp)

    out_path = generate_checksums(files, tmp_path)
    assert out_path.exists()
    assert out_path.name == "CHECKSUM"

    # Read back via find_sidecar_files using exact name (no glob pattern)
    hashes = find_sidecar_files(tmp_path, "CHECKSUM")
    assert len(hashes) == 2
    assert "x.bin" in hashes
    assert "y.bin" in hashes

    # Verify against the parsed hashes
    report = verify_checksums(files, hashes)
    assert report.total_files == 2
    assert report.files_checked == 2
    assert report.files_passed == 2
    assert report.files_failed == []


def test_empty_file_list() -> None:
    """Empty file list produces a report with total_files=0."""
    report = verify_checksums([], {})
    assert report.total_files == 0
    assert report.files_checked == 0
    assert report.files_passed == 0
    assert report.files_failed == []


def test_chunk_size_consistency(tmp_path: Path) -> None:
    """Different chunk sizes always produce the same hash.

    Content larger than the smallest chunk size forces multiple reads and
    exercises the streaming loop.
    """
    content = b"x" * 200_000
    fp = tmp_path / "large.bin"
    fp.write_bytes(content)

    hash_64k = compute_sha256(fp, chunk_size=64 * 1024)
    hash_1k = compute_sha256(fp, chunk_size=1024)
    hash_1 = compute_sha256(fp, chunk_size=1)

    expected = hashlib.sha256(content).hexdigest()
    assert hash_64k == expected
    assert hash_1k == expected
    assert hash_1 == expected
