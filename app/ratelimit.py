"""Limite de débit en mémoire, par clé (adresse IP), sur une fenêtre glissante.

Suffit pour un seul processus. Avec plusieurs processus ou serveurs, chaque processus
compte de son côté : il faudrait alors un stockage partagé (Redis, par exemple).
"""
import threading
import time
from collections import deque


class RateLimiter:
    def __init__(self, limit: int, window_s: float, clock=time.monotonic):
        self.limit, self.window_s, self.clock = limit, window_s, clock
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()
        self._calls = 0

    def _recent(self, key: str, now: float) -> deque:
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self.window_s:
            hits.popleft()
        return hits

    def _wait(self, hits: deque, now: float) -> float:
        return 0.0 if len(hits) < self.limit else hits[0] + self.window_s - now

    def _purge(self, now: float) -> None:
        """Oublie de temps en temps les clés inactives, pour que la mémoire ne grossisse pas."""
        self._calls += 1
        if self._calls % 1000 == 0:
            for key in [k for k, h in self._hits.items() if not h or h[-1] <= now - self.window_s]:
                del self._hits[key]

    def check(self, key: str) -> float:
        """Secondes à attendre avant la prochaine tentative (0 = autorisée), sans la compter."""
        if self.limit <= 0:
            return 0.0
        with self._lock:
            now = self.clock()
            return self._wait(self._recent(key, now), now)

    def hit(self, key: str) -> None:
        """Compte une tentative."""
        if self.limit <= 0:
            return
        with self._lock:
            now = self.clock()
            self._recent(key, now).append(now)
            self._purge(now)

    def take(self, key: str) -> float:
        """Vérifie et compte en une fois. Renvoie 0 si autorisée, sinon les secondes à attendre."""
        if self.limit <= 0:
            return 0.0
        with self._lock:
            now = self.clock()
            hits = self._recent(key, now)
            wait = self._wait(hits, now)
            if not wait:
                hits.append(now)
            self._purge(now)
            return wait

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
