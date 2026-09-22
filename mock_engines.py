# mock_engines.py
# Cordoba AI, technical assessment starter file. Confidential.
#
# Two mock image generation engines with DELIBERATELY DIFFERENT interfaces.
# Treat them as third-party SDKs you cannot modify.
# Your job is to build your own unified layer on top of them, so that a
# third engine can be added later without changing your core.
#
# Both engines are deterministic: same prompt + same seed = same image.
# That property is what makes your replay command verifiable.
#
# Prompting styles (from each engine's "documentation"):
#   Engine A ("tagline"): expects SHORT comma-separated visual tags,
#     lowercase, no prose. Example: "coastal road, dusk, warm light, fog"
#   Engine B ("verbosa"): expects RICH natural language, one paragraph,
#     responds well to explicit lighting and atmosphere descriptions.
#
# Requires: Pillow  (pip install pillow)

import hashlib
import io
from PIL import Image, ImageDraw


def _render(label: str, prompt: str, seed: int, size=(512, 320)) -> bytes:
    """Deterministic placeholder image: color derived from (prompt, seed)."""
    h = hashlib.sha256(f"{label}|{prompt}|{seed}".encode()).digest()
    bg = (h[0], h[1], h[2])
    img = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(img)
    d.rectangle([8, 8, size[0] - 8, size[1] - 8], outline=(255, 255, 255), width=2)
    d.text((16, 16), f"{label} | seed={seed}", fill=(255, 255, 255))
    d.text((16, 40), prompt[:60], fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Engine A: function-based SDK. Returns raw PNG bytes. Raises on bad input.
# ---------------------------------------------------------------------------

ENGINE_A_VERSION = "tagline-2.3"


def generate(prompt: str, seed: int) -> bytes:
    """Engine A entry point. prompt: comma-separated tags. Returns PNG bytes."""
    if not prompt or len(prompt) > 300:
        raise ValueError("engine A: prompt must be 1..300 chars")
    if not isinstance(seed, int) or seed < 0:
        raise ValueError("engine A: seed must be a non-negative int")
    return _render("ENGINE-A", prompt, seed)


# ---------------------------------------------------------------------------
# Engine B: client-object SDK. Job dict in, result dict out (base64 payload).
# ---------------------------------------------------------------------------

class VerbosaClient:
    """Engine B entry point. Instantiate, then call run(job)."""

    VERSION = "verbosa-1.7"

    def run(self, job: dict) -> dict:
        """
        job = {"text": str, "seed": int, "quality": "draft" | "final"}
        returns {"status": "ok", "image_b64": str, "engine": str, "seed": int}
        or      {"status": "error", "message": str}
        """
        import base64
        text = job.get("text", "")
        seed = job.get("seed", 0)
        quality = job.get("quality", "draft")
        if len(text) < 20:
            return {"status": "error",
                    "message": "engine B expects a descriptive paragraph (min 20 chars)"}
        if quality not in ("draft", "final"):
            return {"status": "error", "message": "unknown quality setting"}
        png = _render(f"ENGINE-B/{quality}", text, seed)
        return {
            "status": "ok",
            "image_b64": base64.b64encode(png).decode(),
            "engine": self.VERSION,
            "seed": seed,
        }
