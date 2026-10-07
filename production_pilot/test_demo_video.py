"""
test_demo_video.py
-------------------
Plain-assert self-test for Customer Demo Mode's backend: WebM validation,
the seek fix, versioned storage with the pointer switch (a failed save
never touches the current demo), startup cleanup, and the /api/demo/*
endpoints — partly on a real uvicorn server (client disconnect mid-upload,
a 300 MB upload that must not block other requests or sit in memory,
replacing while the old file is being streamed). Uses synthetic WebM
shaped like Chrome's MediaRecorder output. No pytest needed:

    python -m production_pilot.test_demo_video
"""

from __future__ import annotations

import contextlib
import io
import socket
import tempfile
import threading
import time
import tracemalloc
from pathlib import Path

from . import demo_video, history
from .demo_video import DemoVideoError

UNKNOWN = b"\x01\xff\xff\xff\xff\xff\xff\xff"


def _check(label: str, actual, expected) -> bool:
    ok = actual == expected
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        print(f"         expected: {expected}")
        print(f"         actual:   {actual}")
    return ok


def _el(el_id: int, payload: bytes) -> bytes:
    return el_id.to_bytes((el_id.bit_length() + 7) // 8, "big") + demo_video._encode_size(len(payload)) + payload


def _block(i: int, size: int = 200) -> bytes:
    return _el(0xA3, b"\x81" + (i % 30000).to_bytes(2, "big") + b"\x80" + bytes(size))


def make_webm(frames: int = 50, *, known_segment: bool = False, seekhead: bool = False, cluster: bool = True) -> bytes:
    """Chrome-MediaRecorder-like WebM: EBML header, Segment (unknown size),
    Info without Duration, Tracks, one unknown-size Cluster of SimpleBlocks."""
    header = _el(0x1A45DFA3, _el(0x4286, b"\x01") + _el(0x4282, b"webm"))
    info = _el(0x1549A966, _el(0x2AD7B1, (1_000_000).to_bytes(3, "big")) + _el(0x4D80, b"Chrome") + _el(0x5741, b"Chrome"))
    tracks = _el(0x1654AE6B, _el(0xAE, _el(0xD7, b"\x01") + _el(0x86, b"V_VP8")))
    blocks = b"".join(_block(i) for i in range(frames))
    clusters = (bytes.fromhex("1F43B675") + UNKNOWN + _el(0xE7, b"\x00") + blocks) if cluster else b""
    body = (_el(0x114D9B74, _el(0x4DBB, b"\x00")) if seekhead else b"") + info + tracks + clusters
    segment = bytes.fromhex("18538067") + (demo_video._encode_size(len(body), 8) if known_segment else UNKNOWN) + body
    return header + segment


def _raises(fn, *args) -> bool:
    try:
        fn(*args)
    except DemoVideoError:
        return True
    return False


def _files() -> list[str]:
    return sorted(p.name for p in demo_video.DEMO_DIR.iterdir()) if demo_video.DEMO_DIR.exists() else []


def _upload(data: bytes, duration: float = 20.0) -> dict:
    path = demo_video.new_upload_path()
    path.write_bytes(data)
    return demo_video.store(path, duration)


def test_file_handling(tmp: Path) -> list[bool]:
    print("--- WebM validation / seek fix ---")
    r = []
    good = tmp / "good.webm"
    good.write_bytes(make_webm())
    r.append(_check("MediaRecorder-like WebM validates", _raises(demo_video.validate, good), False))
    r.append(_check("it has no Duration (the seek problem)", demo_video.read_duration_seconds(good), None))
    for name, data in (("empty", b""), ("garbage", b"not a video at all" * 10), ("no cluster", make_webm(cluster=False)),
                       ("truncated header", make_webm()[:30])):
        bad = tmp / f"bad-{name.replace(' ', '-')}.webm"
        bad.write_bytes(data)
        r.append(_check(f"rejected: {name}", _raises(demo_video.validate, bad), True))
    fixed = tmp / "fixed.webm"
    demo_video.fix_duration(good, fixed, 20.5)
    r.append(_check("duration fix writes Duration (20.5 s)", round(demo_video.read_duration_seconds(fixed), 3), 20.5))
    again = tmp / "again.webm"
    demo_video.fix_duration(fixed, again, 42.0)
    r.append(_check("re-fix replaces the Duration (no duplicate)",
                    (round(demo_video.read_duration_seconds(again), 3), again.stat().st_size == fixed.stat().st_size),
                    (42.0, True)))
    known = tmp / "known.webm"
    known.write_bytes(make_webm(known_segment=True))
    known_fixed = tmp / "known-fixed.webm"
    demo_video.fix_duration(known, known_fixed, 9.0)
    h = demo_video._parse_header(known_fixed.read_bytes())
    r.append(_check("known-size Segment grows by the inserted bytes",
                    h["segment_size"], known_fixed.stat().st_size - h["segment_size_pos"] - h["segment_size_len"]))
    sk = tmp / "seekhead.webm"
    sk.write_bytes(make_webm(seekhead=True))
    r.append(_check("SeekHead present -> refuses to shift offsets", _raises(demo_video.fix_duration, sk, tmp / "x.webm", 5.0), True))
    r.append(_check("limits are named constants (10 min / 500 MB)",
                    (demo_video.MAX_DURATION_SECONDS, demo_video.MAX_SIZE_BYTES), (600, 500 * 1024 * 1024)))
    r.append(_check("duration limits: 0 and > 10 min rejected, 600 s accepted",
                    (_raises(demo_video.validate_duration, 0), _raises(demo_video.validate_duration, 700),
                     demo_video.validate_duration(600)), (True, True, 600.0)))
    return r


def test_versioned_storage(tmp: Path) -> list[bool]:
    print()
    print("--- versioned storage / pointer switch / cleanup ---")
    r = []
    demo_video.DEMO_DIR = tmp / "store" / "demo"

    first = _upload(make_webm(10), 12.0)
    v1 = first["version"]
    r.append(_check("first recording: current, no previous",
                    (first["exists"], first["has_previous"], v1.startswith("demo-")), (True, False, True)))
    second = _upload(make_webm(20), 15.0)
    v2 = second["version"]
    r.append(_check("second recording: pointer switches to the new version, first kept as previous",
                    (v2 != v1, second["has_previous"], demo_video.video_path("previous").name), (True, True, v1)))
    third = _upload(make_webm(30), 18.0)
    r.append(_check("third recording: the first (older than previous) is cleaned up",
                    _files(), sorted(["current.json", third["version"], v2])))

    before = demo_video.video_path().read_bytes()
    for name, data in (("invalid file", b"\x00" * 1000), ("empty", b"")):
        try:
            _upload(data)
            ok = False
        except DemoVideoError:
            ok = True
        r.append(_check(f"failed save ({name}) -> error, current demo and pointer untouched",
                        (ok, demo_video.video_path().read_bytes() == before, demo_video.status()["version"]),
                        (True, True, third["version"])))
    r.append(_check("... and no temp files left behind", _files(), sorted(["current.json", third["version"], v2])))

    # Replace while the current file is open (a player streaming it — on
    # Windows an open file can't be deleted or replaced).
    current = demo_video.video_path()
    with current.open("rb") as streaming:
        head = streaming.read(100)
        fourth = _upload(make_webm(40), 21.0)
        fifth = _upload(make_webm(50), 24.0)  # makes the streamed file "older than previous"
        rest = streaming.read()
        r.append(_check("replace twice while the old file is being streamed: no error, old stream reads to the end",
                        head + rest == before, True))
    r.append(_check("... the new demo is current", demo_video.status()["version"], fifth["version"]))
    demo_video.cleanup_orphans()
    r.append(_check("... the superseded file is removed once nobody reads it (startup cleanup)",
                    _files(), sorted(["current.json", fifth["version"], fourth["version"]])))

    # Orphans from an interrupted upload / crash, cleaned up on startup.
    for junk in (".upload-dead.webm", ".upload-dead.seekable.webm", ".current.json.x.tmp", "demo-19990101T000000Z-aaaaaa.webm"):
        (demo_video.DEMO_DIR / junk).write_bytes(b"junk")
    removed = demo_video.cleanup_orphans()
    r.append(_check("startup cleanup removes orphaned temp files and unreferenced versions",
                    (sorted(removed), _files()),
                    (sorted([".upload-dead.webm", ".upload-dead.seekable.webm", ".current.json.x.tmp",
                             "demo-19990101T000000Z-aaaaaa.webm"]),
                     sorted(["current.json", fifth["version"], fourth["version"]]))))

    # Current file missing (deleted by hand) -> previous becomes current.
    demo_video.video_path().unlink()
    r.append(_check("current file vanished -> the previous good version is served",
                    (demo_video.status()["version"], demo_video.status()["has_previous"]), (fourth["version"], False)))

    # Legacy single-file demo (older build, e.g. the existing recording).
    demo_video.DEMO_DIR = tmp / "legacy" / "demo"
    demo_video.DEMO_DIR.mkdir(parents=True)
    legacy = tmp / "legacy-src.webm"
    legacy.write_bytes(make_webm(10))
    demo_video.fix_duration(legacy, demo_video.DEMO_DIR / "demo.webm", 12.3)
    (demo_video.DEMO_DIR / "demo.json").write_text(
        '{"duration_seconds": 12.3, "size_bytes": 1, "recorded_at": "2026-10-07T10:26:39Z", "seek_fix": "duration-fix"}')
    legacy_bytes = (demo_video.DEMO_DIR / "demo.webm").read_bytes()
    demo_video.cleanup_orphans()
    st = demo_video.status()
    r.append(_check("legacy demo.webm is adopted as the current version, content unchanged",
                    (st["exists"], st["recorded_at"], st["duration_seconds"], demo_video.video_path().read_bytes() == legacy_bytes,
                     sorted(_files())), (True, "2026-10-07T10:26:39Z", 12.3, True, sorted(["current.json", st["version"]]))))
    r.append(_check("delete removes every version", (demo_video.delete(), demo_video.status()["exists"], _files()),
                    (True, False, [])))
    return r


def test_endpoints(tmp: Path) -> list[bool]:
    print()
    print("--- /api/demo/* endpoints (TestClient) ---")
    from fastapi.testclient import TestClient

    import server

    demo_video.DEMO_DIR = tmp / "api" / "data" / "demo"
    client = TestClient(server.app)
    service_token = server._create_session("service")
    service = {"Authorization": f"Bearer {service_token}"}
    management = {"Authorization": f"Bearer {server._create_session('management')}"}
    webm = make_webm(200)
    url = "/api/demo/video?duration_seconds=20"
    up = {"Content-Type": "video/webm"}

    st = client.get("/api/demo/status").json()
    r = [
        _check("status without demo", (st["exists"], st["version"], st["has_previous"], st["show_for_all"]), (False, None, False, False)),
        _check("upload without session -> 401", client.post(url, content=webm, headers=up).status_code, 401),
        _check("upload as management -> 403", client.post(url, content=webm, headers={**up, **management}).status_code, 403),
    ]
    res = client.post(url, content=webm, headers={**up, **service})
    r.append(_check("upload as service -> 200, stored", (res.status_code, res.json()["exists"], res.json()["duration_seconds"]),
                    (200, True, 20.0)))
    first_version = res.json()["version"]
    stored = demo_video.video_path().read_bytes()

    for label, kwargs, code in (
        ("invalid file -> 422", dict(url=url, content=b"broken" * 100, headers={**up, **service}), 422),
        ("missing duration -> 422", dict(url="/api/demo/video", content=webm, headers={**up, **service}), 422),
        ("duration > 10 min -> 422", dict(url="/api/demo/video?duration_seconds=700", content=webm, headers={**up, **service}), 422),
        ("empty body -> 422", dict(url=url, content=b"", headers={**up, **service}), 422),
        ("wrong content type -> 415", dict(url=url, content=webm, headers={"Content-Type": "image/png", **service}), 415),
    ):
        res = client.post(**kwargs)
        r.append(_check(f"{label}, JSON detail, old demo kept",
                        (res.status_code, bool(res.json().get("detail")), demo_video.video_path().read_bytes() == stored),
                        (code, True, True)))
    original_max = demo_video.MAX_SIZE_BYTES
    demo_video.MAX_SIZE_BYTES = 1000
    try:
        res = client.post(url, content=webm, headers={**up, **service})
        r.append(_check("over the size limit -> 413 JSON (body drained, not a dropped connection), old demo kept",
                        (res.status_code, "MB" in res.json()["detail"], demo_video.video_path().read_bytes() == stored),
                        (413, True, True)))
    finally:
        demo_video.MAX_SIZE_BYTES = original_max
    r.append(_check("no temp files left after failed uploads", _files(), ["current.json", first_version]))

    r.append(_check("GET video, setting OFF, no session -> 401", client.get("/api/demo/video").status_code, 401))
    r.append(_check("GET video, setting OFF, management -> 403", client.get("/api/demo/video", headers=management).status_code, 403))
    res = client.get(f"/api/demo/video?token={service_token}&v=1")
    r.append(_check("GET video with the service token in the URL -> 200 video/webm",
                    (res.status_code, res.headers["content-type"], res.content == stored), (200, "video/webm", True)))
    client.put("/api/service/demo-settings", json={"show_for_all": True}, headers=service)
    res = client.get("/api/demo/video", headers={"Range": "bytes=100-199"})
    r.append(_check("Range request -> 206 with exactly the requested bytes",
                    (res.status_code, res.headers.get("content-range"), res.content == stored[100:200]),
                    (206, f"bytes 100-199/{len(stored)}", True)))
    r.append(_check("which=previous without a previous version -> 404",
                    client.get("/api/demo/video?which=previous").status_code, 404))
    res = client.post(url, content=make_webm(300), headers={**up, **service})
    r.append(_check("second upload replaces the first; the first is served as which=previous (player fallback)",
                    (res.json()["has_previous"], client.get("/api/demo/video?which=previous").content == stored,
                     client.get("/api/demo/video").content != stored), (True, True, True)))
    r.append(_check("cache headers: no-cache + ETag", (res.status_code, "etag" in client.get("/api/demo/video").headers,
                                                       client.get("/api/demo/video").headers.get("cache-control")),
                    (200, True, "no-cache")))
    r.append(_check("DELETE as management -> 403", client.delete("/api/demo/video", headers=management).status_code, 403))
    res = client.delete("/api/demo/video", headers=service)
    r.append(_check("DELETE as service -> gone", (res.status_code, res.json()["exists"], _files()), (200, False, [])))
    r.append(_check("GET video after delete -> 404", client.get("/api/demo/video").status_code, 404))
    client.put("/api/service/demo-settings", json={"show_for_all": False}, headers=service)
    return r


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _big_webm_chunks(total_bytes: int, block: int = 64 * 1024):
    """A valid WebM of ~total_bytes, generated on the fly (never in memory)."""
    yield make_webm(0)
    sent, i = 0, 0
    while sent < total_bytes:
        chunk = b"".join(_block(i + k, block) for k in range(16))
        i += 16
        sent += len(chunk)
        yield chunk


def test_real_server(tmp: Path) -> list[bool]:
    print()
    print("--- real uvicorn server: disconnect, large upload, replace while streaming ---")
    import httpx
    import uvicorn

    import server

    demo_video.DEMO_DIR = tmp / "live" / "data" / "demo"
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    srv = uvicorn.Server(uvicorn.Config(server.app, host="127.0.0.1", port=port, lifespan="off", log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    token = server._create_session("service")
    auth = {"Authorization": f"Bearer {token}", "Content-Type": "video/webm"}
    r = []
    try:
        res = httpx.post(f"{base}/api/demo/video?duration_seconds=12", content=make_webm(100), headers=auth)
        first = res.json()["version"]
        first_bytes = demo_video.video_path().read_bytes()

        # Client disconnects mid-upload (tab closed): headers announce 5 MB, 1 MB is sent, then the socket closes.
        with socket.create_connection(("127.0.0.1", port)) as s:
            s.sendall((f"POST /api/demo/video?duration_seconds=12 HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer {token}\r\n"
                       f"Content-Type: video/webm\r\nContent-Length: {5 * 1024 * 1024}\r\n\r\n").encode())
            s.sendall(make_webm(0) + bytes(1024 * 1024))
        time.sleep(1.0)
        r.append(_check("client disconnects mid-upload -> current demo unchanged and playable, temp file removed",
                        (httpx.get(f"{base}/api/demo/status").json()["version"],
                         httpx.get(f"{base}/api/demo/video?token={token}").content == first_bytes, _files()),
                        (first, True, ["current.json", first])))

        # 300 MB upload: other requests stay responsive, memory stays flat.
        latencies = []
        stop = threading.Event()

        def poll():
            with httpx.Client(timeout=10) as c:
                while not stop.is_set():
                    t0 = time.perf_counter()
                    c.get(f"{base}/api/health")
                    latencies.append(time.perf_counter() - t0)
                    time.sleep(0.05)

        poller = threading.Thread(target=poll)
        tracemalloc.start()
        poller.start()
        t0 = time.perf_counter()
        res = httpx.post(f"{base}/api/demo/video?duration_seconds=60", content=_big_webm_chunks(300 * 1024 * 1024),
                         headers=auth, timeout=300)
        upload_seconds = time.perf_counter() - t0
        stop.set()
        poller.join()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        r.append(_check(f"300 MB upload stored ({upload_seconds:.1f} s)", (res.status_code, res.json()["size_bytes"] > 300 * 1024 * 1024),
                        (200, True)))
        r.append(_check(f"... other requests kept answering during it (max {max(latencies) * 1000:.0f} ms over {len(latencies)} polls)",
                        len(latencies) > 10 and max(latencies) < 1.0, True))
        r.append(_check(f"... never held in memory (peak {peak / 1024 / 1024:.1f} MB of Python allocations)",
                        peak < 50 * 1024 * 1024, True))

        # Replace while a Range stream of the current demo is still open.
        big_version = demo_video.status()["version"]
        with httpx.Client(timeout=60) as player:
            with player.stream("GET", f"{base}/api/demo/video?token={token}", headers={"Range": "bytes=0-"}) as resp:
                status_code = resp.status_code
                chunks = resp.iter_bytes()
                received = len(next(chunks))
                res = httpx.post(f"{base}/api/demo/video?duration_seconds=12", content=make_webm(120), headers=auth)
                received += sum(len(c) for c in chunks)
        size = (demo_video.DEMO_DIR / big_version).stat().st_size
        r.append(_check("replace while the old file is streamed -> 200, old stream finishes completely",
                        (status_code, res.status_code, received == size), (206, 200, True)))
        r.append(_check("... the new demo plays", httpx.get(f"{base}/api/demo/video?token={token}").content
                        == demo_video.video_path().read_bytes(), True))
    finally:
        srv.should_exit = True
        thread.join(timeout=10)
    return r


def main() -> bool:
    tmp = Path(tempfile.mkdtemp(prefix="pp_test_demo_"))
    original_dir = demo_video.DEMO_DIR
    history.DB_PATH = tmp / "history.db"
    with contextlib.redirect_stdout(io.StringIO()):
        history.init_db()
    try:
        results = test_file_handling(tmp) + test_versioned_storage(tmp) + test_endpoints(tmp) + test_real_server(tmp)
    finally:
        demo_video.DEMO_DIR = original_dir
    all_passed = all(results)
    print()
    print("ALL PASSED" if all_passed else "SOME FAILED")
    return all_passed


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
