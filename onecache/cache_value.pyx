from sys import getsizeof
from datetime import datetime
from typing import Any


cdef class CacheValue:
    """Dummy class for handling cache values."""

    cdef double access
    cdef double size
    cdef object value
    cdef object expire_at

    def __init__(self, value: Any, expire_at: datetime = None):
        self.size = getsizeof(value)
        self.access = 0

        self.value = value
        self.expire_at = expire_at

    @property
    def size(self):
        return self.size

    @property
    def access(self):
        return self.access

    @property
    def value(self):
        return self.value

    @property
    def expire_at(self):
        return self.expire_at

    def set_expired(self, data):
        self.expire_at = data

    cpdef expired(self):
        """Check if value is expired."""
        if self.expire_at:
            return datetime.utcnow() > self.expire_at
        return False  # pragma: no cover

    cpdef refresh_ttl(self, expire_at: datetime):
        self.expire_at = expire_at

    cpdef increment(self):
        self.access += 1

    def __eq__(self, otherinstance: "CacheValue"):
        return self.value == otherinstance.value
