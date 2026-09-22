"""Replay a past generation from the journal alone and verify it byte for byte."""
from __future__ import annotations

from dataclasses import dataclass

from studio.engines.base import EngineError
from studio.environment import capture_environment, describe_differences
from studio.errors import ReplayError
from studio.journal import Journal
from studio.models import GenerationRequest
from studio.registry import Registry
from studio.store import ArtifactStore, sha256_bytes


@dataclass(frozen=True)
class ReplayResult:
    generation_id: int
    engine: str
    identical: bool
    stored_sha256: str
    new_sha256: str
    replay_path: str
    notes: tuple[str, ...]


def replay_generation(generation_id: int, *, registry: Registry, store: ArtifactStore,
                      journal: Journal, author: str) -> ReplayResult:
    """Uses only stored values: never the brief, never the optimizer."""
    row = journal.get_generation(generation_id)
    if row.status != "ok":
        raise ReplayError(f"generation {generation_id} failed originally ({row.error}); nothing to replay")
    try:
        adapter = registry.get(row.engine)
    except KeyError:
        raise ReplayError(f"engine '{row.engine}' is not installed; cannot replay generation {generation_id}") from None

    notes: list[str] = []
    if adapter.version != row.engine_version:
        notes.append(f"engine version changed: journal has {row.engine_version}, installed is {adapter.version}")
    notes += [f"environment: {d}" for d in describe_differences(row.env, capture_environment())]

    request = GenerationRequest(row.prompt, row.seed, dict(row.params))
    try:
        result = adapter.generate(request)
    except EngineError as exc:
        raise ReplayError(f"engine failed during replay: {exc}") from exc

    artifact = store.save_replay(row.id, result.image_bytes)
    identical = artifact.sha256 == row.output_sha256

    try:
        if sha256_bytes(store.read(row.output_path)) != row.output_sha256:
            notes.append("the stored image file no longer matches its journal hash")
    except FileNotFoundError:
        notes.append("the original image file is missing (replay does not need it)")

    journal.add_replay(generation_id=row.id, author=author, engine_version=adapter.version,
                       new_sha256=artifact.sha256, identical=identical)
    return ReplayResult(row.id, row.engine, identical, row.output_sha256, artifact.sha256,
                        artifact.path, tuple(notes))
