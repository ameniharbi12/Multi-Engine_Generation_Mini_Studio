"""The contract every engine adapter must follow."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from studio.errors import StudioError
from studio.models import GenerationRequest, GenerationResult, PromptProfile


class EngineError(StudioError):
    """Any engine failure, normalized. Adapters convert SDK failures into this."""


class EngineAdapter(ABC):
    """Wraps one engine SDK behind a single, engine neutral interface."""

    name: str                      # short id used in the CLI and the journal
    version: str                   # engine SDK version, journaled with every image
    profile: PromptProfile         # how to prompt this engine
    # Read only by convention: the runner copies it, never mutates it.
    default_params: ClassVar[dict[str, Any]] = {}

    @abstractmethod
    def generate(self, req: GenerationRequest) -> GenerationResult:
        """Return an image, or raise EngineError. Must be deterministic per (prompt, seed, params)."""

    # Shared input checks, so every adapter rejects bad input the same way.
    def check_params(self, params: dict[str, Any]) -> None:
        unknown = set(params) - set(self.default_params)
        if unknown:
            raise EngineError(
                f"engine '{self.name}' does not accept parameters {sorted(unknown)}; "
                f"it accepts {sorted(self.default_params)}"
            )

    def check_seed(self, seed: Any) -> None:
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise EngineError(f"engine '{self.name}': seed must be a non negative int")

    def check_request(self, req: GenerationRequest) -> None:
        self.check_params(req.params)
        self.check_seed(req.seed)
