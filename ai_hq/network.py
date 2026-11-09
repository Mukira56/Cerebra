"""Create optional HTTP clients only when a user actually uses a connection.

Loading several platform TLS contexts during desktop startup is costly on Windows.
No network connection or TLS setup is needed for the ordinary local workflow.

Every call goes through resilience.send: a connection that fails to open is retried with exponential backoff, a busy
service is retried for reads only, and repeated connection failures pause that service for a moment (circuit breaker).
"""
from threading import Lock

import httpx

from . import resilience


class LazyClient:
    def __init__(self, timeout=30, follow_redirects=False, headers=None):
        self.timeout, self.follow_redirects, self.headers = timeout, follow_redirects, dict(headers or {})
        self._client = None
        self._lock = Lock()
        self.breakers = {}  # one per host: a local service that is down never pauses a remote one

    def _get(self):
        with self._lock:
            if self._client is None:
                timeout = self.timeout if isinstance(self.timeout, httpx.Timeout) else httpx.Timeout(self.timeout, connect=min(10, self.timeout))
                self._client = httpx.Client(timeout=timeout, follow_redirects=self.follow_redirects, headers=self.headers)
            return self._client

    def breaker(self, url):
        host = httpx.URL(str(url)).host
        with self._lock:
            return self.breakers.setdefault(host, resilience.Breaker())

    def request(self, method, url, tries=resilience.TRIES, **kwargs):
        return resilience.send(self._get(), method, url, breaker=self.breaker(url), tries=tries, **kwargs)
    def get(self, url, **kwargs): return self.request("GET", url, **kwargs)
    def post(self, url, **kwargs): return self.request("POST", url, **kwargs)
    def put(self, url, **kwargs): return self.request("PUT", url, **kwargs)
    def delete(self, url, **kwargs): return self.request("DELETE", url, **kwargs)

    def close(self):
        with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None
