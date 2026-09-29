from pathlib import Path
import subprocess  # nosec B404 -- fixed bundled ffmpeg executable; shell is never invoked
from typing import Any, Dict

import imageio_ffmpeg
from imageio_ffmpeg._definitions import FNAME_PER_PLATFORM, get_platform
from imageio_ffmpeg._parsing import parse_ffmpeg_header


class MediaProbeError(RuntimeError):
    pass


FULL_STREAM_TIMEOUT_SECONDS = 180


def _bundled_ffmpeg_exe() -> str:
    """Return only the ffmpeg binary shipped inside the pinned imageio-ffmpeg package."""
    package_root = Path(imageio_ffmpeg.__file__).resolve().parent
    filename = FNAME_PER_PLATFORM.get(get_platform())
    if not filename:
        raise MediaProbeError("bundled_ffmpeg_platform_unsupported")

    binary = (package_root / "binaries" / filename).resolve()
    binaries_root = (package_root / "binaries").resolve()
    if binaries_root not in binary.parents or not binary.is_file():
        raise MediaProbeError("bundled_ffmpeg_missing")
    return str(binary)


def _probe_full_video_stream(path: str) -> Dict[str, Any]:
    """Decode the complete primary video stream and return metadata from the same run."""
    ffmpeg = _bundled_ffmpeg_exe()
    command = [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "info",
        "-nostats",
        "-err_detect",
        "explode",
        "-xerror",
        "-i",
        path,
        "-map",
        "0:v:0",
        "-an",
        "-sn",
        "-dn",
        "-f",
        "null",
        "-",
    ]
    try:
        # Fixed package-owned executable + argv list + shell=False. Neither
        # IMAGEIO_FFMPEG_EXE nor PATH participates in executable selection.
        result = subprocess.run(  # nosec B603
            command,
            check=False,
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=FULL_STREAM_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaProbeError("video_full_stream_probe_timeout") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise MediaProbeError("video_full_stream_probe_failed") from exc

    diagnostic = result.stderr.decode("utf-8", errors="replace")
    if result.returncode != 0:
        raise MediaProbeError("video_full_stream_corrupt")

    try:
        meta = parse_ffmpeg_header(diagnostic)
    except Exception as exc:
        raise MediaProbeError("video_metadata_parse_failed") from exc

    size = meta.get("size") or meta.get("source_size") or (0, 0)
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


def probe_video(path: str) -> Dict[str, Any]:
    """Measure server-side metadata while decoding the complete stream through EOF."""
    return _probe_full_video_stream(path)


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
