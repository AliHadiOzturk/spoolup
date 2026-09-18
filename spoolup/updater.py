"""In-app updater: git fetch/ff-merge + pip install, state persistence.

Non-destructive only: fetch + merge --ff-only. No force, no stash, no reset.
"""

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class Updater:
    def __init__(self, repo_root: str, state_path: str):
        self.repo_root = repo_root
        self.state_path = state_path
        self._lock = threading.Lock()

    # ---------- git plumbing ----------
    def git_available(self) -> bool:
        try:
            subprocess.run(
                ["git", "--version"],
                capture_output=True,
                check=True,
                timeout=10,
            )
            return True
        except Exception:
            return False

    def _sanitize(self, text: str) -> str:
        # strip credentials embedded in remote URLs: scheme://user:pass@host
        return re.sub(r"(https?://)[^\s@]+@", r"\1***@", text or "")

    def _run(self, cmd: List[str], timeout: int = 120) -> subprocess.CompletedProcess:
        return subprocess.run(
            cmd,
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def check(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "ok": False, "error": None, "current": "", "latest": "",
            "ahead_by": 0, "commits": [],
        }
        if not self.git_available():
            result["error"] = "git not available"
            return result
        try:
            fetch = self._run(["git", "fetch", "origin", "main"], timeout=60)
            if fetch.returncode != 0:
                result["error"] = self._sanitize(fetch.stderr.strip()[-300:])
                return result
            current = self._run(["git", "rev-parse", "HEAD"]).stdout.strip()
            latest = self._run(["git", "rev-parse", "origin/main"]).stdout.strip()
            log = self._run(
                ["git", "log", "--format=%h%x09%s", "HEAD..origin/main"]
            ).stdout.strip()
            commits = []
            if log:
                for line in log.splitlines():
                    h, _, subject = line.partition("\t")
                    commits.append({"hash": h, "subject": subject})
            result.update({
                "ok": True, "current": current, "latest": latest,
                "ahead_by": len(commits), "commits": commits,
            })
        except Exception as e:
            result["error"] = self._sanitize(str(e))[:300]
        return result

    def apply(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "ok": False, "error": None, "steps": [], "changed": False,
        }
        try:
            fetch = self._run(["git", "fetch", "origin", "main"], timeout=60)
            result["steps"].append({
                "cmd": "git fetch origin main",
                "rc": fetch.returncode,
                "tail": self._sanitize((fetch.stdout + fetch.stderr).strip()[-300:]),
            })
            if fetch.returncode != 0:
                result["error"] = "fetch failed"
                return result
            before = self._run(["git", "rev-parse", "HEAD"]).stdout.strip()
            merge = self._run(["git", "merge", "--ff-only", "origin/main"])
            result["steps"].append({
                "cmd": "git merge --ff-only origin/main",
                "rc": merge.returncode,
                "tail": self._sanitize((merge.stdout + merge.stderr).strip()[-300:]),
            })
            if merge.returncode != 0:
                result["error"] = "merge failed (local changes?)"
                return result
            after = self._run(["git", "rev-parse", "HEAD"]).stdout.strip()
            result["changed"] = before != after

            reqs = os.path.join(self.repo_root, "requirements.txt")
            if os.path.exists(reqs):
                pip = self._run(
                    [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                    timeout=600,
                )
                result["steps"].append({
                    "cmd": "pip install -r requirements.txt",
                    "rc": pip.returncode,
                    "tail": self._sanitize((pip.stdout + pip.stderr).strip()[-300:]),
                })
                if pip.returncode != 0:
                    result["error"] = "dependency install failed"
                    return result
            result["ok"] = True
        except Exception as e:
            result["error"] = self._sanitize(str(e))[:300]
        return result

    # ---------- state ----------
    def get_state(self) -> Dict[str, Any]:
        defaults: Dict[str, Any] = {
            "pending_restart": False, "last_check": None,
            "last_apply": None, "ts": None,
        }
        if not os.path.exists(self.state_path):
            return defaults
        try:
            with open(self.state_path, "r") as f:
                data = json.load(f)
            defaults.update({k: data.get(k) for k in defaults if k in data})
        except Exception as e:
            logger.warning("update state unreadable: %s", e)
        return defaults

    def set_state(self, **values: Any) -> None:
        with self._lock:
            state = self.get_state()
            state.update(values)
            parent = os.path.dirname(os.path.abspath(self.state_path))
            os.makedirs(parent, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=parent, suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(state, f, indent=2)
                os.replace(tmp, self.state_path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
