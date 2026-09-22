"""Error types the CLI reports as a clean message instead of a traceback."""


class StudioError(Exception):
    """Base class for expected, user facing failures."""


class PromptError(StudioError):
    """A prompt does not satisfy the target engine's limits."""


class ReplayError(StudioError):
    """A generation cannot be replayed."""
