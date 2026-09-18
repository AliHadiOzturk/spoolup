"""Watchdog: periodic self-heal sweeps for 24/7 unattended operation.

Runs a list of registered checks every `interval` seconds. A check returns
(ok, message, heal_fn); on not-ok the heal_fn runs (idempotent runtime
restart paths) and a banner is published to the dashboard. A crashing check
never kills the watchdog.
"""

import logging
import threading
from typing import Any, Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)

CheckResult = Optional[Tuple[bool, str, Optional[Callable[[], None]]]]


class Watchdog:
    def __init__(self, interval: int = 30):
        self.interval = max(5, int(interval))
        self.banners: List[str] = []
        self._checks: List[Tuple[str, Callable[[], CheckResult]]] = []
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def register_check(
        self, name: str, check: Callable[[], CheckResult]
    ) -> None:
        self._checks.append((name, check))

    def add_banner(self, message: str) -> None:
        self.banners.append(message)
        if len(self.banners) > 20:
            del self.banners[: len(self.banners) - 20]

    def _run_checks(self) -> None:
        for name, check in list(self._checks):
            try:
                result = check()
            except Exception as e:
                logger.error("watchdog check %s crashed: %s", name, e)
                continue
            if result is None:
                continue
            ok, message, heal_fn = result
            if ok:
                continue
            logger.warning("watchdog: %s — %s", name, message)
            self.add_banner("watchdog: %s" % message)
            if heal_fn is not None:
                try:
                    heal_fn()
                except Exception as e:
                    logger.error("watchdog heal for %s failed: %s", name, e)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()

        def loop():
            while not self._stop.wait(self.interval):
                self._run_checks()

        self._thread = threading.Thread(
            target=loop, daemon=True, name="spoolup-watchdog"
        )
        self._thread.start()
        logger.info("Watchdog started (interval=%ds)", self.interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
