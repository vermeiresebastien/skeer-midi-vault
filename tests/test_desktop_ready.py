"""The desktop launcher's readiness wait, gated on the cost of a real answer.

Shipped 1.1.1 asked `/api/health` 80 times with a 1.2 s socket timeout per
attempt. That endpoint answers by reporting on the index, and one honest answer
on the owner's 450 MB library measured 2.27 s — so every attempt gave up a
moment too early, the wait concluded the service was dead, and the launcher took
a working service down with it. Both directions are pinned here: an answer that
is slow but real must become ready, and a service that never answers must not
hang forever.
"""
from __future__ import annotations

import time
import unittest

import desktop

# Measured 2026-11-22 against a copy of a 48,516-file index: integrity_check
# 1.72 s + foreign_key_check 0.42 s + coverage scan 0.13 s, with the file cache
# warm. A floor, not a ceiling.
SLOWEST_HONEST_ANSWER = 2.27


class ReadinessWaitTests(unittest.TestCase):
    def test_an_answer_slower_than_the_old_timeout_becomes_ready(self) -> None:
        seen_timeouts: list[float] = []

        def probe(url: str, timeout: float) -> bool:
            seen_timeouts.append(timeout)
            return timeout >= SLOWEST_HONEST_ANSWER

        started = time.monotonic()
        ready = desktop._wait_until_ready("http://127.0.0.1:9/", probe=probe)

        self.assertTrue(ready, f"every attempt was cut off at {max(seen_timeouts)} s")
        self.assertGreaterEqual(
            min(seen_timeouts), SLOWEST_HONEST_ANSWER,
            "a per-attempt timeout below the cost of one health answer is what "
            "made a healthy 1.1.1 launch report a dead service")
        self.assertLess(time.monotonic() - started, 2.0)

    def test_a_service_that_never_answers_fails_inside_the_budget(self) -> None:
        started = time.monotonic()
        ready = desktop._wait_until_ready(
            "http://127.0.0.1:9/", budget_seconds=0.5, pause=0.05,
            probe=lambda url, timeout: False)

        self.assertFalse(ready)
        self.assertLess(time.monotonic() - started, 1.5)


if __name__ == "__main__":
    unittest.main()
