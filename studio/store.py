"""Saves image files and fingerprints them. Knows nothing about engines or SQL."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Artifact:
    path: str      # relative to the store root, always with forward slashes
    sha256: str


class ArtifactStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def save_generation(self, run_id: str, engine: str, seed: int, data: bytes) -> Artifact:
        self._check_name(run_id)
        self._check_name(engine)
        return self._write(f"{run_id}/{engine}/seed{seed}.png", data)

    def save_replay(self, generation_id: int, data: bytes) -> Artifact:
        return self._write(f"replays/gen{generation_id}.png", data)

    def read(self, relative_path: str) -> bytes:
        return self.full_path(relative_path).read_bytes()

    def full_path(self, relative_path: str) -> Path:
        path = (self.root / relative_path).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError(f"path escapes the output folder: {relative_path}")
        return path

    def _write(self, relative_path: str, data: bytes) -> Artifact:
        path = self.full_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return Artifact(relative_path, sha256_bytes(data))

    @staticmethod
    def _check_name(name: str) -> None:
        if not _SAFE_NAME.match(name) or set(name) == {"."}:
            raise ValueError(f"unsafe name for a folder: {name!r}")
