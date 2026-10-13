from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ledger import LedgerError


RENDERER_VERSION = "TRENDHUNTER_LOCAL_CARD_VIDEO_V1"


@dataclass(frozen=True)
class RenderResult:
    media_path: str
    sha256: str
    size_bytes: int
    duration_seconds: float
    width: int
    height: int
    fps: int
    renderer_version: str = RENDERER_VERSION


def _sha256_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            size += len(chunk)
            h.update(chunk)
    return h.hexdigest(), size


def _pick_font(size: int):
    try:
        from PIL import ImageFont
    except Exception as exc:  # pragma: no cover - guarded by preflight
        raise LedgerError("Local media renderer requires Pillow") from exc

    candidates = [
        os.environ.get("TRENDHUNTER_FONT_PATH"),
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            try:
                return ImageFont.truetype(str(candidate), size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap(text: str, *, width: int = 34) -> list[str]:
    import textwrap

    clean = " ".join(str(text or "").split())
    if not clean:
        return []
    return textwrap.wrap(clean, width=width, break_long_words=False, break_on_hyphens=False)


def _raqm_available() -> bool:
    try:
        from PIL import features
        return bool(features.check_feature("raqm"))
    except Exception:
        return False


def _prepare_draw_text(value: str) -> tuple[str, str | None]:
    """Prepare complex RTL text safely across Pillow builds.

    Prefer Pillow/Raqm when present.  On Windows builds where FriBiDi/Raqm is
    unavailable, shape Arabic with arabic-reshaper and resolve bidi ordering
    with python-bidi, then draw the already-prepared visual string without
    passing Pillow's direction= argument.
    """
    text = str(value or "")
    if not _contains_arabic(text):
        return text, None

    if _raqm_available():
        return text, "rtl"

    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
    except Exception as exc:
        raise LedgerError(
            "Arabic rendering requires Pillow Raqm or the fallback packages "
            "arabic-reshaper and python-bidi"
        ) from exc

    return get_display(arabic_reshaper.reshape(text)), None


def _draw_text(
    draw: Any,
    xy: tuple[int, int],
    text: str,
    *,
    font: Any,
    fill: tuple[int, int, int],
) -> None:
    prepared, direction = _prepare_draw_text(text)
    kwargs: dict[str, Any] = {"font": font, "fill": fill}
    if direction:
        kwargs["direction"] = direction
    draw.text(xy, prepared, **kwargs)


def _slide_png(path: Path, *, title: str, body: str, footer: str, width: int, height: int) -> None:
    try:
        from PIL import Image, ImageDraw
    except Exception as exc:  # pragma: no cover
        raise LedgerError("Local media renderer requires Pillow") from exc

    img = Image.new("RGB", (width, height), (17, 24, 39))
    draw = ImageDraw.Draw(img)
    title_font = _pick_font(max(34, width // 22))
    body_font = _pick_font(max(24, width // 34))
    footer_font = _pick_font(max(18, width // 50))

    margin = int(width * 0.07)
    top = int(height * 0.14)
    text_width = max(24, int(width / 25))

    y = top
    for line in _wrap(title, width=max(18, text_width - 8))[:4]:
        _draw_text(draw, (margin, y), line, font=title_font, fill=(244, 247, 251))
        y += int(title_font.size * 1.35) if hasattr(title_font, "size") else 48

    y += int(height * 0.04)
    for line in _wrap(body, width=text_width)[:12]:
        _draw_text(draw, (margin, y), line, font=body_font, fill=(205, 215, 228))
        y += int(body_font.size * 1.45) if hasattr(body_font, "size") else 36

    footer_lines = _wrap(footer, width=text_width + 8)[:3]
    fy = height - margin - (len(footer_lines) * 30)
    for line in footer_lines:
        _draw_text(draw, (margin, fy), line, font=footer_font, fill=(118, 195, 255))
        fy += 30

    img.save(path, format="PNG", optimize=True)


def _contains_arabic(value: str) -> bool:
    return any("\u0600" <= ch <= "\u06ff" for ch in str(value or ""))


def _ffmpeg_executable() -> str:
    explicit = os.environ.get("TRENDHUNTER_FFMPEG_PATH")
    if explicit and Path(explicit).is_file():
        return explicit
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            return exe
    except Exception:
        pass
    raise LedgerError(
        "Local media renderer requires ffmpeg. Install imageio-ffmpeg or provide TRENDHUNTER_FFMPEG_PATH."
    )


class LocalCreativeVideoRenderer:
    """Deterministic local renderer for the governed creative payload.

    It does not fetch remote media, does not publish, and does not invent factual data.
    The current implementation intentionally renders a clean, text-led short video from
    the exact governed creative fields. Future richer renderers can replace it behind the
    same governed descriptor boundary without weakening exact-media authorization.
    """

    def __init__(self, *, width: int = 1080, height: int = 1920, fps: int = 30, seconds_per_slide: int = 4):
        self.width = int(width)
        self.height = int(height)
        self.fps = int(fps)
        self.seconds_per_slide = int(seconds_per_slide)
        if self.width <= 0 or self.height <= 0 or self.fps <= 0 or self.seconds_per_slide <= 0:
            raise LedgerError("Invalid local renderer geometry")

    def render(self, creative_payload: dict[str, Any], output_path: str | Path) -> RenderResult:
        if not isinstance(creative_payload, dict):
            raise LedgerError("CREATIVE_ARTIFACT payload must be structured")
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        title = str(creative_payload.get("title") or "").strip()
        hook = str(creative_payload.get("hook") or "").strip()
        body = str(creative_payload.get("body") or "").strip()
        description = str(creative_payload.get("description") or "").strip()
        cta = str(creative_payload.get("cta") or "").strip()
        hashtags = creative_payload.get("hashtags") if isinstance(creative_payload.get("hashtags"), list) else []
        target = creative_payload.get("target") if isinstance(creative_payload.get("target"), dict) else {}

        if not title or not body:
            raise LedgerError("Video rendering requires non-empty creative title and body")

        footer = " · ".join(
            x for x in [
                str(target.get("platform") or "").strip(),
                str(target.get("publication_language") or target.get("language") or "").strip(),
                str(target.get("target_market") or target.get("jurisdiction") or target.get("region") or "").strip(),
            ] if x
        )
        hashtag_text = " ".join(str(x) for x in hashtags[:8])

        slides = [
            (title, hook or description or body, footer),
            ("الفكرة" if _contains_arabic(body) else "The idea", body, footer),
            ("التفاصيل" if _contains_arabic(description) else "Details", description or body, footer),
            ("شارك رأيك" if _contains_arabic(cta or body) else "Your turn", cta or hashtag_text or description, footer),
        ]

        with tempfile.TemporaryDirectory(prefix="trendhunter-render-") as td:
            tmp = Path(td)
            concat = []
            for idx, (slide_title, slide_body, slide_footer) in enumerate(slides):
                png = tmp / f"slide-{idx:02d}.png"
                _slide_png(
                    png,
                    title=slide_title,
                    body=slide_body,
                    footer=slide_footer,
                    width=self.width,
                    height=self.height,
                )
                concat.append(f"file '{png.as_posix()}'")
                concat.append(f"duration {self.seconds_per_slide}")
            concat.append(f"file '{(tmp / f'slide-{len(slides)-1:02d}.png').as_posix()}'")
            concat_file = tmp / "concat.txt"
            concat_file.write_text("\n".join(concat) + "\n", encoding="utf-8")

            ffmpeg = _ffmpeg_executable()
            cmd = [
                ffmpeg,
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-vf", f"fps={self.fps},format=yuv420p",
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "20",
                "-movflags", "+faststart",
                str(output),
            ]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if proc.returncode != 0 or not output.is_file():
                raise LedgerError("Local ffmpeg render failed: " + (proc.stderr[-1600:] if proc.stderr else "unknown error"))

        digest, size = _sha256_file(output)
        return RenderResult(
            media_path=str(output),
            sha256=digest,
            size_bytes=size,
            duration_seconds=float(len(slides) * self.seconds_per_slide),
            width=self.width,
            height=self.height,
            fps=self.fps,
        )


def renderer_contract_fingerprint() -> str:
    payload = {
        "renderer_version": RENDERER_VERSION,
        "format": "mp4/h264/yuv420p",
        "remote_assets": False,
        "facts_added": False,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
