import sys, os, subprocess, tempfile, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from spoolup.updater import Updater


def _git_ok():
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def _sh(cmd, cwd, ok=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if ok and r.returncode != 0:
        raise AssertionError("%s failed: %s" % (cmd, r.stderr[-400:]))
    return r


def _make_repos():
    """origin (bare) + work clone with one extra commit on origin."""
    base = tempfile.mkdtemp(prefix="spoolup-updater-")
    origin = os.path.join(base, "origin.git")
    work = os.path.join(base, "work")
    _sh(["git", "init", "--bare", origin], base)
    _sh(["git", "clone", origin, work], base)
    _sh(["git", "config", "user.email", "t@t"], work)
    _sh(["git", "config", "user.name", "t"], work)
    with open(os.path.join(work, "f.txt"), "w") as f:
        f.write("one")
    _sh(["git", "add", "."], work)
    _sh(["git", "commit", "-m", "first"], work)
    _sh(["git", "branch", "-M", "main"], work)
    _sh(["git", "push", "origin", "main"], work)
    # make origin's HEAD point at main so the second clone checks out main
    _sh(["git", "symbolic-ref", "HEAD", "refs/heads/main"], origin)
    # second clone advances origin by one commit
    other = os.path.join(base, "other")
    _sh(["git", "clone", origin, other], base)
    _sh(["git", "config", "user.email", "t@t"], other)
    _sh(["git", "config", "user.name", "t"], other)
    with open(os.path.join(other, "f.txt"), "a") as f:
        f.write("two")
    _sh(["git", "add", "."], other)
    _sh(["git", "commit", "-m", "second commit"], other)
    _sh(["git", "push", "origin", "main"], other)
    return origin, work


def test_git_available():
    u = Updater("/nonexistent", "/nonexistent/state.json")
    assert u.git_available() == _git_ok()


def test_check_reports_ahead_commits():
    if not _git_ok():
        print("SKIP: git unavailable")
        return
    origin, work = _make_repos()
    u = Updater(work, os.path.join(work, "state.json"))
    result = u.check()
    assert result["ok"] is True
    assert result["ahead_by"] == 1
    assert result["commits"][0]["subject"] == "second commit"
    assert result["current"] != result["latest"]


def test_check_up_to_date():
    if not _git_ok():
        print("SKIP: git unavailable")
        return
    origin, work = _make_repos()
    u = Updater(work, os.path.join(work, "state.json"))
    u.apply()
    result = u.check()
    assert result["ok"] is True
    assert result["ahead_by"] == 0
    assert result["commits"] == []


def test_apply_merges_and_reports_change():
    if not _git_ok():
        print("SKIP: git unavailable")
        return
    origin, work = _make_repos()
    u = Updater(work, os.path.join(work, "state.json"))
    u.check()
    before = _sh(["git", "rev-parse", "HEAD"], work).stdout.strip()
    result = u.apply()
    after = _sh(["git", "rev-parse", "HEAD"], work).stdout.strip()
    assert result["ok"] is True
    assert result["changed"] is True
    assert before != after


def test_apply_dirty_tree_fails_safely():
    if not _git_ok():
        print("SKIP: git unavailable")
        return
    origin, work = _make_repos()
    u = Updater(work, os.path.join(work, "state.json"))
    u.check()
    with open(os.path.join(work, "f.txt"), "a") as f:
        f.write("dirty")
    result = u.apply()
    assert result["ok"] is False
    assert result["changed"] is False


def test_state_persist_roundtrip():
    d = tempfile.mkdtemp(prefix="updater-state-")
    u = Updater(d, os.path.join(d, "state.json"))
    assert u.get_state()["pending_restart"] is False
    u.set_state(pending_restart=True, last_check={"ok": True})
    u2 = Updater(d, os.path.join(d, "state.json"))
    st = u2.get_state()
    assert st["pending_restart"] is True
    assert st["last_check"] == {"ok": True}


def test_error_sanitizes_remote_credentials():
    u = Updater("/nonexistent", "/nonexistent/state.json")
    sanitized = u._sanitize(
        "fatal: unable to access 'https://user:secret@github.com/x/y.git/': auth"
    )
    assert "secret" not in sanitized


if __name__ == "__main__":
    test_git_available()
    test_check_reports_ahead_commits()
    test_check_up_to_date()
    test_apply_merges_and_reports_change()
    test_apply_dirty_tree_fails_safely()
    test_state_persist_roundtrip()
    test_error_sanitizes_remote_credentials()
    print("test_updater: ALL PASS")
