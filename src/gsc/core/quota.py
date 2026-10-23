"""Темп и дневные квоты API Google — один источник правды для CLI и библиотеки."""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path

import platformdirs

from ..providers.google import quota_day
from .version import CLI_NAME

INSPECTION_DAILY_LIMIT = 2000  # URL Inspection: запросов в сутки на ресурс
INSPECTION_PER_MINUTE = 600  # и в минуту на ресурс
PAGESPEED_PER_100S = 400  # PageSpeed Insights: запросов за 100 с на ключ


class RateLimiter:
    """Не больше `calls` вызовов за скользящее окно `period` секунд. Потокобезопасен."""

    def __init__(
        self,
        calls: int,
        period: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.calls = calls
        self.period = period
        self._clock = clock
        self._sleep = sleep
        self._stamps: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = self._clock()
                while self._stamps and now - self._stamps[0] >= self.period:
                    self._stamps.popleft()
                if len(self._stamps) < self.calls:
                    self._stamps.append(now)
                    return
                wait = self.period - (now - self._stamps[0])
            self._sleep(wait)


class InspectionQuota:
    """Сколько инспекций уже сделано сегодня (сутки Google, тихоокеанское время) по каждому ресурсу.

    Счётчик локальный — в файле состояния пользователя, общий для всех процессов
    gsc на этой машине. Запросы с других машин или из других программ он не видит,
    поэтому `remaining()` — оценка сверху; точный стоп даёт ответ Google 429.
    """

    def __init__(self, path: Path | None = None, *, limit: int = INSPECTION_DAILY_LIMIT) -> None:
        self.path = path or Path(platformdirs.user_state_dir(CLI_NAME)) / "inspection_quota.json"
        self.limit = limit
        self._lock = threading.Lock()

    def _load(self) -> dict[str, dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except OSError, ValueError:
            return {}
        today = quota_day()
        return {site: entry for site, entry in data.items() if isinstance(entry, dict) and entry.get("day") == today}

    def _save(self, data: dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def remaining(self, site_url: str) -> int:
        entry = self._load().get(site_url, {})
        if entry.get("exhausted"):
            return 0
        return max(0, self.limit - int(entry.get("used", 0)))

    def record(self, site_url: str) -> None:
        with self._lock:
            data = self._load()
            entry = data.setdefault(site_url, {"day": quota_day(), "used": 0})
            entry["used"] = int(entry.get("used", 0)) + 1
            self._save(data)

    def mark_exhausted(self, site_url: str) -> None:
        with self._lock:
            data = self._load()
            data.setdefault(site_url, {"day": quota_day(), "used": self.limit})["exhausted"] = True
            self._save(data)
