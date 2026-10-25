"""Create optional HTTP clients only when a user actually uses a connection.

Loading several platform TLS contexts during desktop startup is costly on Windows.
No network connection or TLS setup is needed for the ordinary local workflow.
"""
from threading import Lock

import httpx


class LazyClient:
    def __init__(self, timeout=30):
        self.timeout = timeout
        self._client = None
        self._lock = Lock()

    def _get(self):
        with self._lock:
            if self._client is None:
                self._client = httpx.Client(timeout=self.timeout, follow_redirects=False)
            return self._client

    def request(self, *args, **kwargs): return self._get().request(*args, **kwargs)
    def get(self, *args, **kwargs): return self._get().get(*args, **kwargs)
    def post(self, *args, **kwargs): return self._get().post(*args, **kwargs)

    def close(self):
        with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None
