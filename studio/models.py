from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

MAX_ELEMENTS = 5
BRIEF_TEXT_FIELDS = ("scene", "lighting", "time_of_day", "mood")


def _require_text(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non empty string")


@dataclass(frozen=True)
class Element:
    """One extra thing in the picture, and where it sits."""
    what: str
    placement: str

    def __post_init__(self) -> None:
        _require_text(self.what, "element 'what'")
        _require_text(self.placement, "element 'placement'")


@dataclass(frozen=True)
class Brief:
    scene: str
    lighting: str
    time_of_day: str
    mood: str
    elements: tuple[Element, ...] = ()

    def __post_init__(self) -> None:
        for name in BRIEF_TEXT_FIELDS:
            _require_text(getattr(self, name), f"brief field '{name}'")
        if len(self.elements) > MAX_ELEMENTS:
            raise ValueError(
                f"a brief allows at most {MAX_ELEMENTS} elements, got {len(self.elements)}"
            )

    @classmethod
    def from_dict(cls, data: dict) -> "Brief":
        """Build a Brief from parsed JSON, with clear errors."""
        unknown = set(data) - set(BRIEF_TEXT_FIELDS) - {"elements"}
        if unknown:
            raise ValueError(f"unknown brief keys: {sorted(unknown)}")
        try:
            elements = tuple(Element(**e) for e in data.get("elements", []))
            return cls(
                scene=data["scene"],
                lighting=data["lighting"],
                time_of_day=data["time_of_day"],
                mood=data["mood"],
                elements=elements,
            )
        except KeyError as exc:
            raise ValueError(f"missing brief field: {exc.args[0]}") from exc
        except TypeError as exc:
            raise ValueError(f"bad element, expected 'what' and 'placement': {exc}") from exc


@dataclass(frozen=True)
class RunConfig:
    """What to run: which engines, which seeds, who is running it."""
    engines: tuple[str, ...]
    seeds: tuple[int, ...]
    author: str
    params_overrides: dict[str, dict] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.engines:
            raise ValueError("choose at least one engine")
        if len(set(self.engines)) != len(self.engines):
            raise ValueError("engines must not repeat")
        if not self.seeds:
            raise ValueError("choose at least one seed")
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError("seeds must not repeat")
        if any(isinstance(s, bool) or not isinstance(s, int) or s < 0 for s in self.seeds):
            raise ValueError("seeds must be non negative integers")
        _require_text(self.author, "author")


@dataclass(frozen=True)
class GenerationRequest:
    """Engine neutral input to any adapter."""
    prompt: str
    seed: int
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class GenerationResult:
    """Engine neutral output from any adapter."""
    image_bytes: bytes
    engine: str
    engine_version: str


@dataclass(frozen=True)
class PromptProfile:
    """How one engine likes to be prompted. Each adapter brings its own."""
    style: str
    min_chars: int
    max_chars: int
    guidance: str                      # what an LLM optimizer would read
    render: Callable[[Brief], str]     # what the rule based optimizer calls


@dataclass(frozen=True)
class PromptResult:
    prompt: str
    optimizer_id: str
    notes: str = ""
