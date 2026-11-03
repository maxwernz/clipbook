import hashlib
import http.server
import json
import threading
from functools import partial
from pathlib import Path

import pytest

from clipbook import updater


def _feed(tmp_path: Path, version="9.9.9", payload=b"new app", sha=None, size=None, key=None) -> Path:
    feed = tmp_path / "feed"
    feed.mkdir()
    (feed / "pkg.zip").write_bytes(payload)
    manifest = {"version": version, "notes": "- neu", "assets": {
        key or updater.platform_key(): {"file": "pkg.zip",
                                        "sha256": sha or hashlib.sha256(payload).hexdigest(),
                                        "size": len(payload) if size is None else size}}}
    (feed / "latest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return feed


def test_versions():
    assert updater.parse_version("v1.2") == (1, 2, 0)
    assert updater.is_newer("0.10.0", "0.9.9")
    assert not updater.is_newer("0.2.0", "0.2.0")


def test_check_and_download_from_folder(tmp_path):
    feed = _feed(tmp_path)
    res = updater.check([str(feed)], current="0.1.0")
    assert res.release and res.release.version == "9.9.9"
    path = updater.download(res.release, tmp_path / "dl")
    assert path.read_bytes() == b"new app"


def test_no_update_when_current(tmp_path):
    feed = _feed(tmp_path, version="0.1.0")
    assert updater.check([str(feed)], current="0.1.0").release is None


def test_no_package_for_this_platform(tmp_path):
    feed = _feed(tmp_path, key="some-other-os")
    res = updater.check([str(feed)], current="0.1.0")
    assert res.release is None and res.latest == "9.9.9"


def test_bad_checksum_is_rejected(tmp_path):
    feed = _feed(tmp_path, sha="0" * 64)
    rel = updater.check([str(feed)], current="0.1.0").release
    with pytest.raises(updater.UpdateError, match="Prüfsumme"):
        updater.download(rel, tmp_path / "dl")
    assert not list((tmp_path / "dl").glob("*"))      # nothing half-downloaded left behind


def test_wrong_size_is_rejected(tmp_path):
    feed = _feed(tmp_path, size=999)
    rel = updater.check([str(feed)], current="0.1.0").release
    with pytest.raises(updater.UpdateError, match="unvollständig"):
        updater.download(rel, tmp_path / "dl")


def test_unreachable_sources_are_skipped(tmp_path):
    good = _feed(tmp_path)
    res = updater.check([str(tmp_path / "missing"), "https://127.0.0.1:9/latest.json", str(good)],
                        current="0.1.0")
    assert res.release and len(res.errors) == 2


def test_invalid_manifest(tmp_path):
    (tmp_path / "latest.json").write_text("{kaputt", encoding="utf-8")
    res = updater.check([str(tmp_path)], current="0.1.0")
    assert res.release is None and "ungültig" in res.errors[0]


def test_http_feed(tmp_path):
    feed = _feed(tmp_path)
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(feed))
    handler.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_port}/updates"
        # folder URL without latest.json -> 404, explicit json URL works and resolves the file relatively
        res = updater.check([f"http://127.0.0.1:{srv.server_port}/latest.json"], current="0.1.0")
        assert res.release.asset_location.endswith("/pkg.zip")
        assert updater.download(res.release, tmp_path / "dl").read_bytes() == b"new app"
        assert updater.check([url], current="0.1.0").release is None
    finally:
        srv.shutdown()


def test_feed_order(tmp_path):
    class Lib:
        root = tmp_path
        config = {"update_feed": "https://intern.example/updates"}
    feeds = updater.feed_candidates("/device/feed", Lib())
    assert feeds[0] == "/device/feed" and feeds[1] == "https://intern.example/updates"
    assert feeds[2] == str(tmp_path / "updates") and feeds[-1] == updater.GITHUB_FEED


def test_dev_version_cannot_self_update():
    ok, reason = updater.can_self_update()
    assert not ok and "Entwicklungsversion" in reason


def test_versions_match():
    import re
    from clipbook import __version__
    py = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'^version = "([^"]+)"', py, re.M).group(1) == __version__
