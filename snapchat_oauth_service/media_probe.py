from contextlib import suppress
import subprocess  # nosec B404 -- fixed ffmpeg executable; shell is never invoked
from typing import Any, Dict

import imageio_ffmpeg


class MediaProbeError(RuntimeError):
    pass


FULL_STREAM_TIMEOUT_SECONDS = 180


def _verify_full_video_stream(path: str) -> None:
    """Decode the complete primary video stream and fail on any decode error."""
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
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
        # The executable is obtained from the pinned imageio-ffmpeg package and
        # the media path is passed as one argv element. shell=False is explicit.
        result = subprocess.run(  # nosec B603
            command,
            check=False,
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=FULL_STREAM_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MediaProbeError("video_full_stream_probe_failed") from exc

    if result.returncode != 0:
        raise MediaProbeError("video_full_stream_corrupt")


def probe_video(path: str) -> Dict[str, Any]:
    """Measure metadata and decode the complete video stream before accepting it."""
    reader = None
    try:
        # imageio-ffmpeg parses stream metadata from ffmpeg's diagnostic output.
        # Do not force "-v error" here because that suppresses the metadata
        # needed to determine duration and frame size.
        reader = imageio_ffmpeg.read_frames(path, pix_fmt="rgb24")
        meta = next(reader)
        size = meta.get("size") or (0, 0)
        width = int(size[0] or 0)
        height = int(size[1] or 0)
        duration = float(meta.get("duration") or 0.0)
        codec = str(meta.get("codec") or "")
        if width <= 0 or height <= 0 or duration <= 0:
            raise MediaProbeError("video_metadata_incomplete")

        # Metadata at the beginning of a container is not sufficient. A file can
        # begin normally and become corrupt later. Force ffmpeg to decode the
        # primary video stream through EOF before returning a successful probe.
        _verify_full_video_stream(path)

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
