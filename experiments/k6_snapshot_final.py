"""Bounded k6 snapshot integrity and SHA-256 verification."""

import hashlib
import os
import stat

from experiments.traffic_evidence_p15 import TrafficEvidenceError

MAX_BYTES = 64 * 1024 * 1024


def fingerprint(path):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)

    fd = os.open(str(path), flags)

    try:
        before = os.fstat(fd)

        if not stat.S_ISREG(before.st_mode):
            raise TrafficEvidenceError("k6 capture is not a regular file")

        if not 0 < before.st_size <= MAX_BYTES:
            raise TrafficEvidenceError("invalid k6 capture size")

        digest = hashlib.sha256()
        total = 0

        while True:
            chunk = os.read(fd, 65536)

            if not chunk:
                break

            total += len(chunk)

            if total > MAX_BYTES:
                raise TrafficEvidenceError("k6 capture exceeds limit")

            digest.update(chunk)

        after = os.fstat(fd)

        if (
            total != before.st_size
            or before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns
        ):
            raise TrafficEvidenceError("k6 capture changed during read")

        return {
            "sha256": digest.hexdigest(),
            "size": total,
            "device": after.st_dev,
            "inode": after.st_ino,
            "mtime_ns": after.st_mtime_ns,
            "ctime_ns": after.st_ctime_ns,
        }

    finally:
        os.close(fd)


def assert_unchanged(path, expected):
    actual = fingerprint(path)

    if actual != expected:
        raise TrafficEvidenceError(
            "k6 capture changed after manifest validation"
        )

    return actual
