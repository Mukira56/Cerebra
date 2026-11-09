"""Retries, exponential backoff and a circuit breaker for Cerebra's calls to outside services.

Which failures are retried:
- A connection that never opened (refused, dropped or timed out while connecting) is retried for any method:
  nothing reached the service, so even a send or a payment request cannot be done twice.
- A read timeout, or a 429/502/503/504 answer, is retried only for GET, HEAD and OPTIONS. A POST that may have
  reached the service is never repeated here; the caller decides (outreach and uploads reserve an operation first).

Waits grow 0.5 s, 1 s, 2 s... with a little random jitter, capped at 8 s, and honour a short Retry-After.

The circuit breaker belongs to one connection (one LazyClient). After five connections in a row fail to open, the
service is left alone for 30 seconds. Services on this computer (127.0.0.1, localhost, such as Ollama) get no retries
and no breaker: a refused local connection means the program isn't running, and waiting would not help. Calls in that time fail at once with ServicePaused (an httpx.ConnectError,
so existing error handling treats it as "could not be reached"). After the pause one trial call goes through: if it
works the breaker closes, and if it fails the pause starts again.
"""
import random
import threading
import time

import httpx

from . import logs

TRIES = 3
BASE_WAIT = 0.5
MAX_WAIT = 8.0
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
RETRY_STATUS = {429, 502, 503, 504}
FAILURES_TO_OPEN = 5
PAUSE_SECONDS = 30.0

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

sleep = time.sleep  # replaced in tests
clock = time.monotonic
log = logs.get("network")


class ServicePaused(httpx.ConnectError):
    """The circuit breaker is open: the service failed to connect repeatedly a moment ago."""


class Breaker:
    def __init__(self, failures_to_open=FAILURES_TO_OPEN, pause=PAUSE_SECONDS):
        self.failures_to_open, self.pause = failures_to_open, pause
        self.failures, self.opened_at, self.trial = 0, None, False
        self.lock = threading.Lock()

    def state(self):
        with self.lock:
            if self.opened_at is None:
                return "closed"
            return "open" if clock() - self.opened_at < self.pause else "half-open"

    def allow(self):
        with self.lock:
            if self.opened_at is None:
                return True
            if clock() - self.opened_at < self.pause or self.trial:
                return False
            self.trial = True  # one trial call after the pause
            return True

    def success(self):
        with self.lock:
            self.failures, self.opened_at, self.trial = 0, None, False

    def failure(self, host=""):
        with self.lock:
            self.failures += 1
            reopened = self.trial
            self.trial = False
            if reopened or self.failures >= self.failures_to_open:
                self.opened_at = clock()
                log.warning("%s could not be reached %d times in a row; leaving it alone for %d seconds",
                            host or "A service", self.failures, int(self.pause))


def wait_for(attempt, response=None):
    """Seconds before the next try: exponential with jitter, or a short Retry-After from the service."""
    if response is not None:
        value = response.headers.get("retry-after", "")
        if value.strip().isdigit():
            return min(float(value), MAX_WAIT)
    return min(BASE_WAIT * (2 ** attempt), MAX_WAIT) + random.uniform(0, BASE_WAIT / 2)


def send(client, method, url, breaker=None, tries=TRIES, **options):
    """client.request with the retry rules above. Returns the last response; raises the last error."""
    method = str(method).upper()
    host = httpx.URL(url).host if isinstance(url, (str, httpx.URL)) else ""
    if host in LOCAL_HOSTS:
        return client.request(method, url, **options)
    for attempt in range(max(1, tries)):
        last = attempt == max(1, tries) - 1
        if breaker is not None and not breaker.allow():
            raise ServicePaused(f"{host or 'The service'} failed to connect several times just now; Cerebra will try again in a moment")
        try:
            response = client.request(method, url, **options)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            if breaker is not None:
                breaker.failure(host)
            if last:
                raise
            log.info("Connection to %s failed (%s); retrying", host, exc.__class__.__name__)
            sleep(wait_for(attempt))
            continue
        except (httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
            if breaker is not None:
                breaker.success()  # it connected: the service is up, only this answer failed
            if last or method not in SAFE_METHODS:
                raise
            log.info("%s %s gave no answer (%s); retrying", method, host, exc.__class__.__name__)
            sleep(wait_for(attempt))
            continue
        if breaker is not None:
            breaker.success()
        if response.status_code in RETRY_STATUS and method in SAFE_METHODS and not last:
            log.info("%s %s answered %d; retrying", method, host, response.status_code)
            pause = wait_for(attempt, response)
            response.close()
            sleep(pause)
            continue
        return response
    raise AssertionError("unreachable")
