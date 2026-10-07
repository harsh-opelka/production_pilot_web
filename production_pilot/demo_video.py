"""
demo_video.py
--------------
Customer Demo Mode: the ONE recorded demo video (a browser tab recording,
WebM from MediaRecorder) that the dashboard loops on a trade-fair screen.
Storage and validation only — server.py has the endpoints, the frontend
records and plays it (lib/demoRecorder.js, DemoOverlay.svelte).

Stored under data/demo/ in the project root as versioned files plus a
small pointer file (see "storage" below): a failed or interrupted upload
never touches the demo that is being played, and the previous good
version is kept as a fallback for the player.

Seeking: MediaRecorder WebM has no Duration and no Cues, so a <video>
can't show the length or jump around reliably. If ffmpeg is on PATH the
upload is remuxed (stream copy, no re-encode), which writes both. Without
ffmpeg, fix_duration() writes the Duration into the Segment Info, which
is enough for Chromium to seek (together with HTTP Range requests).
"""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent.parent / "data" / "demo"

#: Safety limits for one recording. The ONLY definition: the frontend gets
#: them from GET /api/demo/status (see limits()).
MAX_DURATION_SECONDS = 30 * 60
#: The recorder warns this long before the automatic stop.
DURATION_WARNING_SECONDS = 2 * 60
MAX_SIZE_BYTES = 1024 * 1024 * 1024
#: Free disk space required before a recording may start.
MIN_FREE_DISK_BYTES = 2 * 1024 * 1024 * 1024
#: The client's stopwatch and the recorder can disagree by a little.
DURATION_GRACE_SECONDS = 5

_FFMPEG_TIMEOUT_SECONDS = 600

# EBML / Matroska element IDs (with their length-marker bits).
_EBML = 0x1A45DFA3
_DOCTYPE = 0x4282
_SEGMENT = 0x18538067
_SEEKHEAD = 0x114D9B74
_INFO = 0x1549A966
_TIMECODE_SCALE = 0x2AD7B1
_DURATION = 0x4489
_TRACKS = 0x1654AE6B
_CLUSTER = 0x1F43B675

#: How far into the file the header elements (EBML header, Info, Tracks)
#: are searched for — they're always right at the start.
_HEADER_SCAN_BYTES = 1024 * 1024


class DemoVideoError(ValueError):
    """Invalid / unusable recording — the message is shown to the technician."""


class DemoStorageError(DemoVideoError):
    """Not enough free disk space, or the recording is over the size limit."""


class DemoSessionError(DemoVideoError):
    """Unknown / expired upload session, or a chunk at the wrong offset."""


# --- EBML parsing -------------------------------------------------------------

def _read_id(buf: bytes, pos: int) -> tuple[int, int]:
    """Element ID (marker bits kept, as IDs are written) and its length."""
    first = buf[pos]
    length = next((n for n in range(1, 5) if first & (0x80 >> (n - 1))), 0)
    if not length or pos + length > len(buf):
        raise DemoVideoError("Not a WebM file (bad element ID)")
    return int.from_bytes(buf[pos:pos + length], "big"), length


def _read_size(buf: bytes, pos: int) -> tuple[int | None, int]:
    """Element data size (None = "unknown size", as live recorders write
    for Segment/Cluster) and the length of the size field."""
    first = buf[pos]
    length = next((n for n in range(1, 9) if first & (0x80 >> (n - 1))), 0)
    if not length or pos + length > len(buf):
        raise DemoVideoError("Not a WebM file (bad element size)")
    value = int.from_bytes(buf[pos:pos + length], "big") & ((1 << (7 * length)) - 1)
    return (None if value == (1 << (7 * length)) - 1 else value), length


def _encode_size(value: int, length: int | None = None) -> bytes:
    """`value` as an EBML size field (shortest, or exactly `length` bytes)."""
    needed = next(n for n in range(1, 9) if value < (1 << (7 * n)) - 1)
    length = length or needed
    if needed > length:
        raise DemoVideoError("Element too large to patch in place")
    return ((1 << (7 * length)) | value).to_bytes(length, "big")


def _children(buf: bytes, start: int, end: int):
    """(id, data_start, data_size, element_start, size_field_length) for each
    child in buf[start:end]. Stops at an unknown-size child (a Cluster) —
    only the header elements before the first Cluster are ever needed."""
    pos = start
    while pos < end:
        el_id, id_len = _read_id(buf, pos)
        size, size_len = _read_size(buf, pos + id_len)
        data_start = pos + id_len + size_len
        yield el_id, data_start, size, pos, size_len
        if size is None:
            return
        pos = data_start + size


def _parse_header(buf: bytes) -> dict:
    """Locates the parts of a WebM header fix_duration()/validate need.
    Raises DemoVideoError if the bytes are not a usable WebM recording."""
    if len(buf) < 4 or int.from_bytes(buf[:4], "big") != _EBML:
        raise DemoVideoError("Not a WebM file")
    _, id_len = _read_id(buf, 0)
    ebml_size, size_len = _read_size(buf, id_len)
    ebml_end = id_len + size_len + (ebml_size or 0)
    doctype = None
    for el_id, data_start, size, _, _ in _children(buf, id_len + size_len, ebml_end):
        if el_id == _DOCTYPE:
            doctype = buf[data_start:data_start + size].rstrip(b"\x00").decode("ascii", "replace")
    if doctype not in ("webm", "matroska"):
        raise DemoVideoError(f"Not a WebM file (doctype {doctype!r})")

    seg_id, seg_id_len = _read_id(buf, ebml_end)
    if seg_id != _SEGMENT:
        raise DemoVideoError("WebM file has no Segment")
    seg_size, seg_size_len = _read_size(buf, ebml_end + seg_id_len)
    seg_data = ebml_end + seg_id_len + seg_size_len
    seg_end = len(buf) if seg_size is None else min(len(buf), seg_data + seg_size)

    info = tracks = cluster = seekhead = None
    for el_id, data_start, size, el_start, size_len in _children(buf, seg_data, seg_end):
        if el_id == _INFO:
            info = (el_start, data_start, size)
        elif el_id == _TRACKS:
            tracks = True
        elif el_id == _SEEKHEAD:
            seekhead = True
        elif el_id == _CLUSTER:
            cluster = True
            break
    if info is None or not tracks or not cluster:
        raise DemoVideoError("WebM file contains no video (missing Info, Tracks or Cluster)")
    return {
        "segment_size_pos": ebml_end + seg_id_len,
        "segment_size": seg_size,
        "segment_size_len": seg_size_len,
        "info": info,
        "has_seekhead": bool(seekhead),
    }


def validate(path: Path) -> None:
    """Raises DemoVideoError unless `path` is a non-empty WebM recording
    with at least one video cluster."""
    if not path.exists() or path.stat().st_size == 0:
        raise DemoVideoError("The recording is empty")
    with path.open("rb") as f:
        _parse_header(f.read(_HEADER_SCAN_BYTES))


def read_duration_seconds(path: Path) -> float | None:
    """The Duration stored in the file's Segment Info, or None if it has none."""
    with path.open("rb") as f:
        buf = f.read(_HEADER_SCAN_BYTES)
    h = _parse_header(buf)
    _, info_data, info_size = h["info"]
    scale = 1_000_000
    duration = None
    for el_id, data_start, size, _, _ in _children(buf, info_data, info_data + info_size):
        value = buf[data_start:data_start + size]
        if el_id == _TIMECODE_SCALE:
            scale = int.from_bytes(value, "big")
        elif el_id == _DURATION:
            duration = struct.unpack(">f" if size == 4 else ">d", value)[0]
    return None if duration is None else duration * scale / 1e9


def fix_duration(src: Path, dst: Path, duration_seconds: float) -> None:
    """Writes `src` to `dst` with a Duration in the Segment Info (replaced
    if present, inserted otherwise). Only the header is rewritten; the rest
    is streamed through. Raises DemoVideoError if the layout can't be
    patched safely (a SeekHead would hold offsets that the insert shifts)."""
    with src.open("rb") as f:
        buf = f.read(_HEADER_SCAN_BYTES)
    h = _parse_header(buf)
    info_start, info_data, info_size = h["info"]
    info_end = info_data + info_size

    scale = 1_000_000
    kept = []
    for el_id, data_start, size, el_start, _ in _children(buf, info_data, info_end):
        if el_id == _TIMECODE_SCALE:
            scale = int.from_bytes(buf[data_start:data_start + size], "big")
        if el_id != _DURATION:
            kept.append(buf[el_start:data_start + size])
    duration_el = _DURATION.to_bytes(2, "big") + _encode_size(8) + struct.pack(">d", duration_seconds * 1e9 / scale)
    body = b"".join(kept) + duration_el
    new_info = _INFO.to_bytes(4, "big") + _encode_size(len(body)) + body
    delta = len(new_info) - (info_end - info_start)
    if delta and h["has_seekhead"]:
        raise DemoVideoError("WebM layout can't be patched (SeekHead present)")

    head = bytearray(buf[:info_start])
    if h["segment_size"] is not None:  # known-size Segment: grow it by delta
        pos = h["segment_size_pos"]
        head[pos:pos + h["segment_size_len"]] = _encode_size(h["segment_size"] + delta, h["segment_size_len"])

    with src.open("rb") as fin, dst.open("wb") as fout:
        fout.write(head)
        fout.write(new_info)
        fin.seek(info_end)
        shutil.copyfileobj(fin, fout, 1024 * 1024)


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _remux(src: Path, dst: Path) -> bool:
    """Stream-copy remux with ffmpeg (adds Duration + Cues). False if ffmpeg
    is missing or fails — the caller falls back to fix_duration()."""
    exe = shutil.which("ffmpeg")
    if exe is None:
        return False
    try:
        result = subprocess.run(
            [exe, "-y", "-v", "error", "-i", str(src), "-c", "copy", "-f", "webm", str(dst)],
            capture_output=True, timeout=_FFMPEG_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and dst.exists() and dst.stat().st_size > 0


# --- storage -------------------------------------------------------------------
#
# Every recording is its own versioned file (demo-<UTC>-<rand>.webm); a small
# pointer file (current.json) says which one is current and which one was
# the previous good version. A new recording is written, validated and made
# seekable completely before the pointer is switched (temp + os.replace),
# so a failed, interrupted or cancelled save can never touch the demo that
# is being played. Old versions are deleted only after the switch; a file
# that is still being streamed (Windows refuses to delete open files) just
# stays until the next save or server start cleans it up.

_POINTER = "current.json"
_switch_lock = threading.Lock()


def _pointer_path() -> Path:
    return DEMO_DIR / _POINTER


def _read_pointer() -> dict:
    """{"current": meta | None, "previous": meta | None}; meta has "file"."""
    try:
        data = json.loads(_pointer_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"current": None, "previous": None}
    result = {}
    for key in ("current", "previous"):
        meta = data.get(key) if isinstance(data, dict) else None
        ok = isinstance(meta, dict) and isinstance(meta.get("file"), str) and (DEMO_DIR / meta["file"]).is_file()
        result[key] = meta if ok else None
    if result["current"] is None and result["previous"] is not None:
        result = {"current": result["previous"], "previous": None}  # current file vanished: fall back
    return result


def _write_pointer(pointer: dict) -> None:
    tmp = DEMO_DIR / f".{_POINTER}.{uuid.uuid4().hex}.tmp"
    tmp.write_text(json.dumps(pointer), encoding="utf-8")
    os.replace(tmp, _pointer_path())


def _version_name() -> str:
    return f"demo-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}.webm"


def _try_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass  # still open (being streamed) - removed by a later cleanup


def _adopt_legacy() -> None:
    """Older builds stored one fixed demo.webm (+ demo.json). Turn it into
    the current version so an existing recording keeps playing."""
    legacy = DEMO_DIR / "demo.webm"
    if _pointer_path().exists() or not legacy.is_file():
        return
    try:
        validate(legacy)
    except DemoVideoError:
        return  # leave an unusable legacy file alone (cleanup removes it)
    try:
        old = json.loads((DEMO_DIR / "demo.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    name = _version_name()
    os.replace(legacy, DEMO_DIR / name)
    meta = {
        "file": name,
        "duration_seconds": old.get("duration_seconds") or read_duration_seconds(DEMO_DIR / name),
        "size_bytes": (DEMO_DIR / name).stat().st_size,
        "recorded_at": old.get("recorded_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seek_fix": old.get("seek_fix"),
    }
    _write_pointer({"current": meta, "previous": None})
    _try_unlink(DEMO_DIR / "demo.json")


def cleanup_orphans() -> list[str]:
    """Startup housekeeping: adopt a legacy demo.webm, then remove leftover
    temp files (interrupted uploads, half-written pointers) and versions the
    pointer no longer references. Returns the names removed."""
    if not DEMO_DIR.is_dir():
        return []
    with _switch_lock:
        _adopt_legacy()
        pointer = _read_pointer()
        keep = {_POINTER} | {m["file"] for m in pointer.values() if m}
        removed = []
        for path in DEMO_DIR.iterdir():
            if path.is_file() and path.name not in keep:
                _try_unlink(path)
                if not path.exists():
                    removed.append(path.name)
        return removed


def video_path(which: str = "current") -> Path | None:
    """The file to stream for "current" or "previous" (None if there is none)."""
    if which not in ("current", "previous"):
        return None
    with _switch_lock:
        _adopt_legacy()
        meta = _read_pointer()[which]
    return DEMO_DIR / meta["file"] if meta else None


def new_upload_path() -> Path:
    """A temp file next to the demos (same filesystem, so os.replace is atomic)."""
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    return DEMO_DIR / f".upload-{uuid.uuid4().hex}.webm"


def validate_duration(duration_seconds) -> float:
    if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, (int, float)) or duration_seconds <= 0:
        raise DemoVideoError("Missing or invalid recording duration")
    if duration_seconds > MAX_DURATION_SECONDS + DURATION_GRACE_SECONDS:
        raise DemoVideoError(f"Recording longer than {MAX_DURATION_SECONDS // 60} minutes")
    return float(duration_seconds)


def store(upload: Path, duration_seconds: float, keep_upload_on_error: bool = False) -> dict:
    """Validates the uploaded temp file, makes it seekable, stores it as a
    new version and only then switches the pointer to it (the old current
    becomes "previous"). Temp files are always cleaned up; on any failure
    the pointer - and so the demo being played - is unchanged. Returns status().
    keep_upload_on_error: leave `upload` in place when saving fails, so the
    finalize step of a chunked upload can be retried."""
    seekable = upload.with_suffix(".seekable.webm")
    ok = False
    try:
        validate(upload)
        if _remux(upload, seekable):
            method = "ffmpeg"
        else:
            fix_duration(upload, seekable, duration_seconds)
            method = "duration-fix"
        validate(seekable)
        stored_duration = read_duration_seconds(seekable) or duration_seconds
        name = _version_name()
        os.replace(seekable, DEMO_DIR / name)  # a NEW name: never touches a file being played
        meta = {
            "file": name,
            "duration_seconds": round(stored_duration, 1),
            "size_bytes": (DEMO_DIR / name).stat().st_size,
            "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "seek_fix": method,
        }
        with _switch_lock:
            _adopt_legacy()
            old = _read_pointer()
            try:
                _write_pointer({"current": meta, "previous": old["current"]})
            except OSError:
                _try_unlink(DEMO_DIR / name)
                raise
            keep = {name} | ({old["current"]["file"]} if old["current"] else set())
            for path in DEMO_DIR.glob("demo-*.webm"):
                if path.name not in keep:
                    _try_unlink(path)  # versions older than "previous"
        ok = True
        return status()
    finally:
        if ok or not keep_upload_on_error:
            _try_unlink(upload)
        _try_unlink(seekable)


# --- chunked upload sessions -------------------------------------------------
#
# The browser uploads the recording WHILE recording (MediaRecorder timeslice
# chunks), appended in order to .session-<id>.webm next to the demos. Each
# chunk carries its byte offset, so a retried chunk that already arrived is
# recognised (no duplicates) and nothing has to be kept in server memory -
# a session survives a server restart. On Stop, finalize_session() runs
# store() on the file. A recording that is never finalized (page closed,
# connection lost) never touches the pointer; its temp file is removed when
# the next recording starts (or by cleanup_orphans() at server start).

_SESSION_PREFIX = ".session-"
_session_lock = threading.Lock()


def limits() -> dict:
    return {
        "max_duration_seconds": MAX_DURATION_SECONDS,
        "duration_warning_seconds": DURATION_WARNING_SECONDS,
        "max_size_bytes": MAX_SIZE_BYTES,
        "min_free_disk_bytes": MIN_FREE_DISK_BYTES,
    }


def free_disk_bytes() -> int:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(DEMO_DIR).free


def _session_path(session_id: str) -> Path:
    if not (isinstance(session_id, str) and len(session_id) == 32 and all(c in "0123456789abcdef" for c in session_id)):
        raise DemoSessionError("Invalid upload session")
    return DEMO_DIR / f"{_SESSION_PREFIX}{session_id}.webm"


def start_session() -> str:
    """Removes partial files of earlier (abandoned) sessions, checks the free
    disk space and creates an empty session file. Returns the session id."""
    with _session_lock:
        DEMO_DIR.mkdir(parents=True, exist_ok=True)
        for path in [*DEMO_DIR.glob(f"{_SESSION_PREFIX}*"), *DEMO_DIR.glob(".upload-*")]:
            _try_unlink(path)
        free = free_disk_bytes()
        if free < MIN_FREE_DISK_BYTES:
            gb = 1024 ** 3
            raise DemoStorageError(
                f"Not enough free disk space on the server: {free / gb:.1f} GB free, "
                f"at least {MIN_FREE_DISK_BYTES / gb:.0f} GB needed"
            )
        session_id = uuid.uuid4().hex
        _session_path(session_id).touch()
        return session_id


def append_chunk(session_id: str, offset: int, data: bytes) -> int:
    """Appends `data` at byte `offset` of the session file. A chunk that is
    already there (a retry whose answer got lost) is accepted without being
    written twice. Returns the new file size."""
    path = _session_path(session_id)
    with _session_lock:
        if not path.is_file():
            raise DemoSessionError("Upload session expired - start a new recording")
        size = path.stat().st_size
        if offset + len(data) <= size:
            return size  # duplicate (retry)
        if offset != size:
            raise DemoSessionError(f"Chunk at offset {offset}, but the server has {size} bytes")
        if size + len(data) > MAX_SIZE_BYTES:
            raise DemoStorageError(f"Recording larger than {MAX_SIZE_BYTES // (1024 * 1024)} MB")
        with path.open("ab") as f:
            f.write(data)
        return size + len(data)


def finalize_session(session_id: str, duration_seconds) -> dict:
    """Validates and stores the session's file (store(): seek fix, atomic
    pointer switch). On failure the file is kept so this can be retried."""
    path = _session_path(session_id)
    duration = validate_duration(duration_seconds)
    with _session_lock:
        if not path.is_file():
            raise DemoSessionError("Upload session expired - start a new recording")
        if path.stat().st_size == 0:
            raise DemoVideoError("The recording is empty")
    return store(path, duration, keep_upload_on_error=True)


def status() -> dict:
    with _switch_lock:
        _adopt_legacy()
        pointer = _read_pointer()
    current, previous = pointer["current"], pointer["previous"]
    if current is None:
        return {"exists": False, "duration_seconds": None, "size_bytes": None, "recorded_at": None,
                "version": None, "has_previous": False, **limits()}
    return {
        **limits(),
        "exists": True,
        "duration_seconds": current.get("duration_seconds"),
        "size_bytes": current.get("size_bytes"),
        "recorded_at": current.get("recorded_at"),
        "version": current["file"],
        "has_previous": previous is not None,
    }


def delete() -> bool:
    """Removes the demo (all versions and the pointer). False if there was none."""
    with _switch_lock:
        _adopt_legacy()
        pointer = _read_pointer()
        existed = pointer["current"] is not None
        _try_unlink(_pointer_path())
        for path in DEMO_DIR.glob("demo-*.webm") if DEMO_DIR.is_dir() else []:
            _try_unlink(path)
    return existed
