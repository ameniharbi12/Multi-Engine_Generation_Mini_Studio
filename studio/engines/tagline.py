"""Adapter for Engine A ("tagline"): function SDK, short lowercase comma separated tags."""
from __future__ import annotations

import mock_engines
from studio.engines.base import EngineAdapter, EngineError
from studio.models import Brief, GenerationRequest, GenerationResult, PromptProfile

MAX_CHARS = 300


def _clean(text: str) -> str:
    return " ".join(text.replace(",", " ").split()).lower()


def render_tags(brief: Brief) -> str:
    """Tags in priority order; least important (last) tags are dropped to fit the limit."""
    tags: list[str] = []
    for value in (brief.scene, brief.time_of_day, brief.lighting, brief.mood):
        tags += [t for t in (_clean(part) for part in value.split(",")) if t]
    tags += [_clean(f"{e.what} {e.placement}") for e in brief.elements]
    tags = list(dict.fromkeys(tags))  # remove duplicates, keep order
    while len(", ".join(tags)) > MAX_CHARS and len(tags) > 1:
        tags.pop()
    return ", ".join(tags)[:MAX_CHARS]


class TaglineAdapter(EngineAdapter):
    name = "tagline"
    version = mock_engines.ENGINE_A_VERSION
    default_params = {}
    profile = PromptProfile(
        style="tagline",
        min_chars=1,
        max_chars=MAX_CHARS,
        guidance=(
            "Write short lowercase visual tags separated by commas. No sentences, no prose. "
            "At most 300 characters. Order by importance: scene, time of day, lighting, mood, "
            "then each extra element with its placement."
        ),
        render=render_tags,
    )

    def generate(self, req: GenerationRequest) -> GenerationResult:
        self.check_request(req)
        try:
            png = mock_engines.generate(req.prompt, req.seed)
        except ValueError as exc:
            raise EngineError(str(exc)) from exc
        return GenerationResult(png, self.name, self.version)


ADAPTER = TaglineAdapter()
