import io
import struct

try:
    import av
except Exception:  # fail closed at validation time if decoder is unavailable
    av = None


class MediaValidationError(ValueError):
    pass


def _u32(buf, off):
    if off < 0 or off + 4 > len(buf):
        raise MediaValidationError("truncated_u32")
    return struct.unpack(">I", buf[off:off+4])[0]


def _iter_boxes(buf, start=0, end=None):
    end = len(buf) if end is None else min(int(end), len(buf))
    pos = int(start)
    while pos + 8 <= end:
        size = _u32(buf, pos)
        kind = bytes(buf[pos+4:pos+8])
        header = 8
        if size == 1:
            if pos + 16 > end:
                raise MediaValidationError("truncated_large_box")
            size = struct.unpack(">Q", buf[pos+8:pos+16])[0]
            header = 16
        elif size == 0:
            size = end - pos
        if size < header or pos + size > end:
            raise MediaValidationError("invalid_box_size")
        yield kind, pos, pos + size, header
        pos += size
    if pos != end:
        # Trailing bytes outside a complete ISO-BMFF box are rejected.
        raise MediaValidationError("trailing_or_truncated_box")


def _find_child(buf, parent_start, parent_end, parent_header, wanted):
    payload_start = parent_start + parent_header
    for kind, start, end, header in _iter_boxes(buf, payload_start, parent_end):
        if kind == wanted:
            return start, end, header
    return None


def _find_track_dimensions(buf, moov):
    moov_start, moov_end, moov_header = moov
    payload_start = moov_start + moov_header
    dimensions = []
    for kind, start, end, header in _iter_boxes(buf, payload_start, moov_end):
        if kind != b"trak":
            continue
        tkhd = _find_child(buf, start, end, header, b"tkhd")
        if not tkhd:
            continue
        ts, te, th = tkhd
        payload = ts + th
        if payload >= te:
            continue
        version = buf[payload]
        # Width/height are the final 8 bytes of tkhd as 16.16 fixed-point.
        # tkhd payload is 84 bytes for version 0 and 96 bytes for version 1.
        if te - ts < th + (96 if version == 1 else 84):
            continue
        width_fixed = _u32(buf, te - 8)
        height_fixed = _u32(buf, te - 4)
        width = width_fixed / 65536.0
        height = height_fixed / 65536.0
        if width > 0 and height > 0:
            dimensions.append((int(round(width)), int(round(height))))
    return dimensions


_CONTAINER_CHILDREN = {
    b"moov", b"trak", b"mdia", b"minf", b"stbl", b"edts", b"dinf", b"udta",
}


def _scan_for_video_sample_entry(buf, start, end):
    found = set()

    def walk(s, e):
        for kind, bs, be, header in _iter_boxes(buf, s, e):
            if kind in (b"avc1", b"avc3", b"hvc1", b"hev1"):
                found.add(kind.decode("ascii"))
            if kind in _CONTAINER_CHILDREN:
                walk(bs + header, be)
            elif kind == b"stsd":
                payload = bs + header
                if payload + 8 > be:
                    raise MediaValidationError("truncated_stsd")
                entry_count = _u32(buf, payload + 4)
                pos = payload + 8
                for _ in range(entry_count):
                    if pos + 8 > be:
                        raise MediaValidationError("truncated_stsd_entry")
                    entry_size = _u32(buf, pos)
                    entry_kind = bytes(buf[pos+4:pos+8])
                    if entry_size < 8 or pos + entry_size > be:
                        raise MediaValidationError("invalid_stsd_entry")
                    if entry_kind in (b"avc1", b"avc3", b"hvc1", b"hev1"):
                        found.add(entry_kind.decode("ascii"))
                    pos += entry_size
    walk(start, end)
    return found


def _decode_probe_h264(blob):
    if av is None:
        raise MediaValidationError("decoder_unavailable")
    try:
        container = av.open(io.BytesIO(bytes(blob)), mode="r", format="mp4")
    except Exception as exc:
        raise MediaValidationError("decoder_open_failed") from exc
    try:
        video_streams = list(container.streams.video)
        if not video_streams:
            raise MediaValidationError("video_stream_required")
        stream = video_streams[0]
        codec_name = str(getattr(stream.codec_context, "name", "") or "").lower()
        if codec_name != "h264":
            raise MediaValidationError("h264_decoder_required")
        width = int(getattr(stream.codec_context, "width", 0) or 0)
        height = int(getattr(stream.codec_context, "height", 0) or 0)
        frame_count = 0
        frame_width = 0
        frame_height = 0
        try:
            for decoded in container.decode(video=stream.index):
                current_width = int(getattr(decoded, "width", 0) or 0)
                current_height = int(getattr(decoded, "height", 0) or 0)
                if current_width <= 0 or current_height <= 0:
                    raise MediaValidationError("decoded_dimensions_invalid")
                if width and height and (current_width != width or current_height != height):
                    raise MediaValidationError("decoded_dimensions_mismatch")
                if frame_count == 0:
                    frame_width = current_width
                    frame_height = current_height
                elif current_width != frame_width or current_height != frame_height:
                    raise MediaValidationError("decoded_frame_dimensions_changed")
                frame_count += 1
        except MediaValidationError:
            raise
        except Exception as exc:
            raise MediaValidationError("h264_decode_failed") from exc
        if frame_count <= 0:
            raise MediaValidationError("h264_frame_required")
        return {
            "codec": codec_name,
            "width": frame_width,
            "height": frame_height,
            "frame_count": frame_count,
        }
    finally:
        try:
            container.close()
        except Exception:
            pass


def validate_mp4(blob, max_bytes, max_duration_sec=None):
    if not isinstance(blob, (bytes, bytearray)) or not blob:
        raise MediaValidationError("empty_media")
    if len(blob) > int(max_bytes):
        raise MediaValidationError("file_too_large")

    top = list(_iter_boxes(blob, 0, len(blob)))
    if not top or top[0][0] != b"ftyp":
        raise MediaValidationError("mp4_ftyp_required")
    moov = next((x[1:] for x in top if x[0] == b"moov"), None)
    mdat = next((x for x in top if x[0] == b"mdat"), None)
    if not moov or not mdat:
        raise MediaValidationError("moov_and_mdat_required")

    # moov tuple is (start,end,header)
    width_height = _find_track_dimensions(blob, moov)
    if not width_height:
        raise MediaValidationError("video_dimensions_unreadable")
    width, height = max(width_height, key=lambda wh: wh[0] * wh[1])
    if width < 240 or height < 240 or width > 4096 or height > 4096:
        raise MediaValidationError("video_dimensions_out_of_policy")
    ratio = width / float(height)
    if ratio < 0.25 or ratio > 4.0:
        raise MediaValidationError("aspect_ratio_out_of_policy")

    codecs = _scan_for_video_sample_entry(blob, moov[0] + moov[2], moov[1])
    # Keep the admission surface deliberately narrow: H.264 only until an
    # independently tested HEVC path is explicitly admitted.
    if not ({"avc1", "avc3"} & codecs):
        raise MediaValidationError("h264_required")

    decoded = _decode_probe_h264(blob)
    if decoded["width"] != width or decoded["height"] != height:
        raise MediaValidationError("track_and_decoder_dimensions_mismatch")

    # Parse mvhd duration.
    mvhd = _find_child(blob, moov[0], moov[1], moov[2], b"mvhd")
    if not mvhd:
        raise MediaValidationError("mvhd_required")
    ms, me, mh = mvhd
    p = ms + mh
    if p >= me:
        raise MediaValidationError("truncated_mvhd")
    version = blob[p]
    if version == 0:
        if p + 20 > me:
            raise MediaValidationError("truncated_mvhd")
        timescale = _u32(blob, p + 12)
        duration = _u32(blob, p + 16)
    elif version == 1:
        if p + 32 > me:
            raise MediaValidationError("truncated_mvhd")
        timescale = _u32(blob, p + 20)
        duration = struct.unpack(">Q", blob[p+24:p+32])[0]
    else:
        raise MediaValidationError("unsupported_mvhd_version")
    if timescale <= 0 or duration <= 0:
        raise MediaValidationError("invalid_duration")
    duration_sec = duration / float(timescale)
    if duration_sec <= 0:
        raise MediaValidationError("invalid_duration")
    if max_duration_sec and duration_sec > float(max_duration_sec):
        raise MediaValidationError("duration_exceeds_creator_limit")

    return {
        "container": "mp4",
        "codec": "h264",
        "width": width,
        "height": height,
        "aspect_ratio": ratio,
        "duration_sec": duration_sec,
        "size_bytes": len(blob),
        "decoded_frame_count": int(decoded.get("frame_count",0)),
    }
