import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from spoolup.sessions import SessionStore


def _store():
    d = tempfile.mkdtemp(prefix="spoolup-sessions-")
    return SessionStore(os.path.join(d, "sessions.json"))


def test_record_start_end_upload_roundtrip():
    s = _store()
    sid = s.record_start("part.gcode", "2026-09-14T10:00:00Z", ["youtube", "kick"])
    s.record_end(sid, "complete")
    s.record_upload(sid, True, detail="vid123")
    sessions = s.list_recent()
    assert len(sessions) == 1
    sess = sessions[0]
    assert sess["filename"] == "part.gcode"
    assert sess["outcome"] == "complete"
    assert sess["platforms"] == ["youtube", "kick"]
    assert sess["upload"] == {"ok": True, "detail": "vid123"}
    assert sess["ended_at"] is not None


def test_sessions_capped_at_50():
    s = _store()
    for i in range(55):
        s.record_start("f%d.gcode" % i, "2026-09-14T10:00:00Z", ["youtube"])
    sessions = s.list_recent()
    assert len(sessions) == 50
    assert sessions[0]["filename"] == "f54.gcode"  # newest first
    assert sessions[-1]["filename"] == "f5.gcode"


def test_corrupted_file_recovers_fresh():
    s = _store()
    with open(s.path, "w") as f:
        f.write("{not json")
    assert s.list_recent() == []
    sid = s.record_start("x.gcode", "2026-09-14T10:00:00Z", [])
    assert s.list_recent()[0]["filename"] == "x.gcode"


def test_atomic_write_no_partial_file():
    s = _store()
    s.record_start("a.gcode", "2026-09-14T10:00:00Z", [])
    assert not os.path.exists(s.path + ".tmp")
    with open(s.path) as f:
        data = json.load(f)
    assert isinstance(data, list)


if __name__ == "__main__":
    test_record_start_end_upload_roundtrip()
    test_sessions_capped_at_50()
    test_corrupted_file_recovers_fresh()
    test_atomic_write_no_partial_file()
    print("test_sessions: ALL PASS")
