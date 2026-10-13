from __future__ import annotations

import email.utils
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable


class ConnectorHTTPError(RuntimeError):
    def __init__(self, message: str, *, failure_class: str, status_code: int | None = None, attempts: int | None = None):
        super().__init__(message)
        self.failure_class = failure_class
        self.status_code = status_code
        self.attempts = attempts


@dataclass(frozen=True)
class HTTPPolicy:
    max_attempts: int = 4
    backoff_base_seconds: float = 0.5
    max_backoff_seconds: float = 8.0
    min_interval_seconds: float = 0.0
    retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504)


class ResilientHTTPClient:
    def __init__(self, policy: HTTPPolicy | None = None, *, opener: Callable | None = None, sleeper: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        self.policy = policy or HTTPPolicy()
        self._opener = opener or urllib.request.urlopen
        self._sleep = sleeper
        self._clock = clock
        self._last_request_at: float | None = None

    def _rate_limit(self) -> None:
        if self.policy.min_interval_seconds <= 0 or self._last_request_at is None:
            return
        delay = self.policy.min_interval_seconds - (self._clock() - self._last_request_at)
        if delay > 0:
            self._sleep(delay)

    @staticmethod
    def _retry_after_seconds(headers) -> float | None:
        if headers is None:
            return None
        value = headers.get("Retry-After")
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                dt = email.utils.parsedate_to_datetime(value)
                return max(0.0, dt.timestamp() - time.time())
            except Exception:
                return None

    @staticmethod
    def _http_failure_class(code: int) -> str:
        if code == 429:
            return "RATE_LIMITED"
        if code in {401, 403}:
            return "UPSTREAM_AUTH_FAILURE"
        if 500 <= code <= 599:
            return "UPSTREAM_5XX"
        return "UPSTREAM_CONTRACT_CHANGED"

    @staticmethod
    def _network_failure_class(exc: BaseException) -> str:
        reason = getattr(exc, "reason", None)
        target = reason if reason is not None else exc
        if isinstance(target, socket.gaierror) or "name resolution" in str(target).lower() or "temporary failure in name" in str(target).lower():
            return "DNS_UNAVAILABLE"
        return "NETWORK_UNAVAILABLE"

    def open(self, request, *, timeout: int = 30) -> bytes:
        last_error: Exception | None = None
        for attempt in range(1, self.policy.max_attempts + 1):
            self._rate_limit()
            try:
                with self._opener(request, timeout=timeout) as resp:
                    raw = resp.read()
                    self._last_request_at = self._clock()
                    return raw
            except urllib.error.HTTPError as exc:
                self._last_request_at = self._clock()
                last_error = exc
                failure_class = self._http_failure_class(exc.code)
                if exc.code not in self.policy.retry_statuses or attempt >= self.policy.max_attempts:
                    raise ConnectorHTTPError(
                        f"HTTP {exc.code} after {attempt} attempt(s)",
                        failure_class=failure_class,
                        status_code=exc.code,
                        attempts=attempt,
                    ) from exc
                retry_after = self._retry_after_seconds(exc.headers)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                self._last_request_at = self._clock()
                last_error = exc
                failure_class = self._network_failure_class(exc)
                if attempt >= self.policy.max_attempts:
                    raise ConnectorHTTPError(
                        f"Network failure after {attempt} attempt(s): {exc}",
                        failure_class=failure_class,
                        attempts=attempt,
                    ) from exc
                retry_after = None
            delay = retry_after if retry_after is not None else min(self.policy.max_backoff_seconds, self.policy.backoff_base_seconds * (2 ** (attempt - 1)))
            self._sleep(delay)
        raise ConnectorHTTPError(str(last_error) if last_error else "HTTP request failed", failure_class="UNKNOWN_FAILURE")
