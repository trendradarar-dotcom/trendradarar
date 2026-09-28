from contextlib import suppress
from typing import Any, Dict

import imageio_ffmpeg


class MediaProbeError(RuntimeError):
    pass


def probe_video(path: str) -> Dict[str, Any]:
    """Read container/video metadata without trusting client-supplied values."""
    reader = None
    try:
        reader = imageio_ffmpeg.read_frames(path, pix_fmt="rgb24", input_params=["-v", "error"])
        meta = next(reader)
        size = meta.get("size") or (0, 0)
        width = int(size[0] or 0)
        height = int(size[1] or 0)
        duration = float(meta.get("duration") or 0.0)
        codec = str(meta.get("codec") or "")
        if width <= 0 or height <= 0 or duration <= 0:
            raise MediaProbeError("video_metadata_incomplete")
        return {
            "width": width,
            "height": height,
            "duration_seconds": duration,
            "codec": codec,
        }
    except (StopIteration, ValueError, OSError, RuntimeError) as exc:
        if isinstance(exc, MediaProbeError):
            raise
        raise MediaProbeError("video_probe_failed") from exc
    finally:
        if reader is not None:
            with suppress(Exception):
                reader.close()


def validate_spotlight_media(meta: Dict[str, Any]) -> list[str]:
    errors: list[str] = []
    duration = float(meta.get("duration_seconds") or 0)
    width = int(meta.get("width") or 0)
    height = int(meta.get("height") or 0)

    # Project production contract is intentionally stricter than Snap's
    # technical 6-60 second limit: 30-60 seconds.
    if duration < 30:
        errors.append("duration_below_internal_30_second_floor")
    if duration > 60:
        errors.append("duration_above_60_second_ceiling")
    if width < 540 or height < 960:
        errors.append("resolution_below_540x960")
    if width > 0 and height > 0:
        ratio = width / height
        if abs(ratio - (9 / 16)) > 0.035:
            errors.append("portrait_ratio_not_9_16_target")
    return errors
