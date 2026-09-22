"""Prompt strategy: turn a Brief into one prompt for one engine.

The interface is shaped so a real LLM can sit behind it (LLMOptimizer below).
The default optimizer is deterministic and rule based.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Callable, Protocol

from studio.errors import PromptError
from studio.models import Brief, PromptProfile, PromptResult


class PromptOptimizer(Protocol):
    id: str

    def optimize(self, brief: Brief, profile: PromptProfile) -> PromptResult: ...


def check_prompt(prompt: str, profile: PromptProfile, engine: str) -> None:
    """Fail before any generation if a prompt breaks the engine's declared limits."""
    size = len(prompt)
    if not profile.min_chars <= size <= profile.max_chars:
        raise PromptError(
            f"prompt for '{engine}' has {size} chars; "
            f"the engine needs {profile.min_chars} to {profile.max_chars}"
        )


class RuleBasedOptimizer:
    """Uses the render function each engine ships with its profile."""

    id = "rule-based-1"

    def optimize(self, brief: Brief, profile: PromptProfile) -> PromptResult:
        return PromptResult(
            prompt=profile.render(brief),
            optimizer_id=self.id,
            notes=f"rendered with the '{profile.style}' profile",
        )


def build_llm_request(brief: Brief, profile: PromptProfile) -> str:
    """The text an LLM would receive. Built from the profile, never from engine names."""
    return (
        "You write image generation prompts.\n"
        f"Target style: {profile.style}\n"
        f"Rules: {profile.guidance}\n"
        f"Length: between {profile.min_chars} and {profile.max_chars} characters.\n"
        "Reply with the prompt only.\n"
        f"Brief (JSON): {json.dumps(asdict(brief))}"
    )


class LLMOptimizer:
    """Same interface, backed by any text completion function (no network code here)."""

    def __init__(self, complete: Callable[[str], str], model: str = "llm") -> None:
        self._complete = complete
        self.id = f"llm-{model}"

    def optimize(self, brief: Brief, profile: PromptProfile) -> PromptResult:
        prompt = self._complete(build_llm_request(brief, profile)).strip()
        return PromptResult(prompt=prompt, optimizer_id=self.id, notes="written by an LLM")
