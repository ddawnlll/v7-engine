"""
SHA-256 batch checksum verification for data lake files.

Provides pure functions for computing SHA-256 hashes of files (memory-efficient
streaming), verifying batches of files against expected hashes, reading
Binance-style CHECKSUM sidecar files, and generating CHECKSUM files.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# ChecksumReport
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChecksumReport:
    """Immutable report of checksum verification results.

    Attributes:
        total_files: Number of files in the verification request.
        files_checked: Number of files actually checked (skipped if no expected
            hash was available).
        files_passed: Number of files whose hash matched the expected value.
        files_failed: List of file paths that failed verification.
        algorithm: Hash algorithm used (default ``"sha256"``).
        generated_at: ISO-8601 timestamp of when this report was built.
    """

    total_files: int
    files_checked: int
    files_passed: int
    files_failed: list[Path] = field(default_factory=list)
    algorithm: str = "sha256"
    generated_at: str = ""


# ---------------------------------------------------------------------------
# Compute
# ---------------------------------------------------------------------------


def compute_sha256(filepath: Path, chunk_size: int = 64 * 1024) -> str:
    """Compute the SHA-256 hex digest of *filepath*.

    Streams the file in *chunk_size* blocks so only a limited amount of data
    resides in memory at any time, making this suitable for large parquet files.

    Returns the lowercase hex digest string.
    """
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


def verify_checksums(
    files: list[Path],
    expected_hashes: dict[str, str],
) -> ChecksumReport:
    """Verify *files* against *expected_hashes*.

    For each file in *files*, looks up ``filepath.name`` in *expected_hashes*.
    If a match is found, the file's actual SHA-256 hash is computed and
    compared.  Files without an entry in *expected_hashes* are skipped.

    Returns a :class:`ChecksumReport` summarising the results.
    """
    total = len(files)
    checked = 0
    passed = 0
    failed: list[Path] = []

    for fp in files:
        expected = expected_hashes.get(fp.name)
        if expected is None:
            continue
        checked += 1
        actual = compute_sha256(fp)
        if actual == expected:
            passed += 1
        else:
            failed.append(fp)

    return ChecksumReport(
        total_files=total,
        files_checked=checked,
        files_passed=passed,
        files_failed=failed,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Sidecar discovery
# ---------------------------------------------------------------------------


def find_sidecar_files(
    directory: Path,
    pattern: str = "*.sha256",
) -> dict[str, str]:
    """Read Binance-style CHECKSUM sidecar files from *directory*.

    Every file in *directory* matching *pattern* is parsed as a checksum
    manifest where each non-empty line is in the format
    ``<hash>  <filename>`` (two spaces between the hash and the filename,
    consistent with ``sha256sum`` output).

    Lines that do not contain the two-space separator are silently skipped.

    Returns a dict mapping filename -> hex hash string.
    """
    result: dict[str, str] = {}
    for sidecar_path in sorted(directory.glob(pattern)):
        text = sidecar_path.read_text()
        for line in text.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            if "  " not in line:
                continue
            hash_part, filename_part = line.split("  ", 1)
            filename = filename_part.strip()
            if filename:
                result[filename] = hash_part.strip()
    return result


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------


def generate_checksums(files: list[Path], output_dir: Path) -> Path:
    """Generate a CHECKSUM file for *files* under *output_dir*.

    The SHA-256 hash of each file is written as a line in the format
    ``<hash>  <filename>``, matching the Binance CHECKSUM convention.  Files
    are written in sorted order to produce deterministic output.

    *output_dir* is created if it does not exist.

    Returns the absolute path of the created CHECKSUM file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "CHECKSUM"

    lines: list[str] = []
    for fp in sorted(files):
        hash_digest = compute_sha256(fp)
        lines.append(f"{hash_digest}  {fp.name}")

    out_path.write_text("\n".join(lines) + "\n")
    return out_path
