"""Adapter for Engine B ("verbosa"): client object SDK, rich natural language paragraph."""
from __future__ import annotations

import base64
import binascii

from mock_engines import VerbosaClient
from studio.engines.base import EngineAdapter, EngineError
from studio.models import Brief, GenerationRequest, GenerationResult, PromptProfile

MIN_CHARS = 20
MAX_CHARS = 1500


def _text(value: str) -> str:
    return " ".join(value.split()).rstrip(".")


def render_paragraph(brief: Brief) -> str:
    """One paragraph with explicit lighting and atmosphere, as the engine's docs recommend."""
    mood, scene = _text(brief.mood), _text(brief.scene)
    article = "An" if mood[:1].lower() in "aeiou" else "A"
    sentences = [
        f"{article} {mood} {scene} at {_text(brief.time_of_day)}.",
        f"The scene is lit by {_text(brief.lighting)}, which shapes soft shadows "
        "and gives the image a clear, tangible atmosphere.",
    ]
    if brief.elements:
        parts = [f"{_text(e.what)}, positioned {_text(e.placement)}" for e in brief.elements]
        sentences.append("The composition includes " + "; ".join(parts) + ".")
    sentences.append(f"The overall mood is {mood}, cinematic and richly detailed.")
    return " ".join(sentences)


class VerbosaAdapter(EngineAdapter):
    name = "verbosa"
    version = VerbosaClient.VERSION
    default_params = {"quality": "draft"}
    profile = PromptProfile(
        style="verbosa",
        min_chars=MIN_CHARS,
        max_chars=MAX_CHARS,
        guidance=(
            "Write one rich paragraph of natural language. Describe the scene, then the lighting "
            "and the atmosphere explicitly, then each extra element with where it sits in the frame."
        ),
        render=render_paragraph,
    )

    def generate(self, req: GenerationRequest) -> GenerationResult:
        self.check_request(req)
        params = {**self.default_params, **req.params}
        job = {"text": req.prompt, "seed": req.seed, "quality": params["quality"]}
        out = VerbosaClient().run(job)
        if out.get("status") != "ok":
            raise EngineError(out.get("message", "engine B returned an unknown error"))
        try:
            png = base64.b64decode(out["image_b64"], validate=True)
        except (KeyError, binascii.Error) as exc:
            raise EngineError("engine B returned an unreadable image payload") from exc
        return GenerationResult(png, self.name, self.version)


ADAPTER = VerbosaAdapter()
