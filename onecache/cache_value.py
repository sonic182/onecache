from datetime import datetime
from sys import getsizeof
from typing import Any


class CacheValue:
    """Dummy class for handling cache values."""

    def __init__(self, value: Any, expire_at: datetime = None):
        self.size = getsizeof(value)
        self.access = 0

        self.value = value
        self.expire_at = expire_at

    def set_expired(self, data):
        self.expire_at = data

    def expired(self):
        """Check if value is expired."""
        if self.expire_at:
            return datetime.utcnow() > self.expire_at
        return False  # pragma: no cover

    def refresh_ttl(self, expire_at: datetime):
        self.expire_at = expire_at

    def increment(self):
        self.access += 1

    def __eq__(self, otherinstance: "CacheValue"):
        return self.value == otherinstance.value
