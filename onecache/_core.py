"""Pure Python cache implementation, used on PyPy or when the extension is unavailable."""

from collections import OrderedDict
from contextlib import nullcontext
from sys import getsizeof
from threading import Lock
from time import monotonic
from typing import Any, Dict, Optional

from onecache.utils import IS_PYPY

INF = float("inf")
_MISSING = object()


class CacheValue:
    """Cache entry holding the value, its expiration (monotonic seconds) and access count."""

    __slots__ = ("value", "expire_at", "size", "access")

    def __init__(self, value: Any, expire_at: float = INF):
        self.value = value
        self.expire_at = expire_at
        self.size = 0
        self.access = 0

    def expired(self, now: Optional[float] = None) -> bool:
        """Check if value is expired."""
        return (monotonic() if now is None else now) > self.expire_at

    def __eq__(self, other):
        if not isinstance(other, CacheValue):
            return NotImplemented
        return self.value == other.value

    __hash__ = None


def _serialize(data: Any):
    if type(data) is str:
        return data
    if isinstance(data, dict):
        return ",".join([f"{key}={_serialize(val)}" for key, val in data.items()])
    if isinstance(data, list):
        return ",".join([_serialize(val) for val in data])
    if isinstance(data, str):
        return data
    return str(data)


def _make_key(args: tuple, kwargs: dict) -> str:
    if not kwargs and len(args) == 1:
        return _serialize(args[0])
    parts = [_serialize(arg) for arg in args]
    if kwargs:
        parts.extend(f"{key}={_serialize(kwargs[key])}" for key in sorted(kwargs))
    return "-".join(parts)


class ExpirableCache:
    """Cache with optional ttl, evicting the oldest inserted entry when full.

    Params:
        * **size (int)**: max items in dict. default=512
        * **timeout (int)**: Timeout in milliseconds, if it is None,
            there is no timeout. default=None
        * **refresh_ttl (int)**: Refresh ttl anytime key is accessed. default=False
        * **thread_safe (bool)**: Tell cache decorator to be thread safe. default=False
        * **max_mem_size (int)**: max mem size inside cache structure. default=None which means no limit.
            For pypy this value is ignored as the objects can change by the JIT compilation.
    """

    _lru = False

    def __init__(
        self,
        size: int = 512,
        timeout: Optional[int] = None,
        refresh_ttl=False,
        thread_safe=False,
        max_mem_size: Optional[int] = None,
    ):
        self.cache: Dict[Any, CacheValue] = OrderedDict()
        self._expiry: Dict[Any, None] = OrderedDict()
        self.timeout = timeout
        self._ttl = timeout / 1000 if timeout else None
        self.size = size
        self.max_mem_size = None if IS_PYPY else max_mem_size
        self.current_size = 0
        self.refresh_ttl = refresh_ttl
        self.thread_safe = thread_safe
        self.lock = Lock() if thread_safe else None
        self._guard = self.lock if thread_safe else nullcontext()

    def get(self, key):
        """Get value of key, None if missing or expired."""
        with self._guard:
            return self._lookup_unlocked(key, None)

    def _lookup(self, key, default=None):
        with self._guard:
            return self._lookup_unlocked(key, default)

    def _lookup_unlocked(self, key, default):
        if self._expiry:
            self._purge_expired(monotonic())
        item = self.cache.get(key)
        if item is None:
            return default
        if item.expire_at != INF:
            now = monotonic()
            if now > item.expire_at:
                self._remove_key(key)
                return default
            if self.refresh_ttl and self._ttl:
                item.expire_at = now + self._ttl
                self._expiry.move_to_end(key)
        if self._lru:
            self.cache.move_to_end(key)
            item.access += 1
        return item.value

    def set(self, key, data):
        """Set value for key, evicting entries if needed."""
        with self._guard:
            self._set_unlocked(key, data)

    def _set_unlocked(self, key, data):
        now = monotonic() if self._ttl or self._expiry else 0.0
        if self._expiry:
            self._purge_expired(now)
        if key in self.cache:
            self._remove_key(key)
        elif self.cache and len(self.cache) >= self.size:
            self._pop_one()

        item = CacheValue(data)
        if self.max_mem_size:
            item.size = getsizeof(key) + getsizeof(data)
            while self.cache and self.current_size + item.size > self.max_mem_size:
                self._pop_one()
            self.current_size += item.size
        self.cache[key] = item
        if self._ttl:
            item.expire_at = now + self._ttl
            self._expiry[key] = None

    def _wrap(self, func, skip_args: bool = False):
        lookup = self._lookup
        set_value = self.set

        def wrapper(*args, **kwargs):
            key = "any" if skip_args else _make_key(args, kwargs)
            value = lookup(key, _MISSING)
            if value is _MISSING:
                value = func(*args, **kwargs)
                set_value(key, value)
            return value

        wrapper.cache = self
        return wrapper

    def _make_key(self, args: tuple, kwargs: dict) -> str:
        return _make_key(args, kwargs)

    def _pop_one(self):
        self._remove_key(next(iter(self.cache)))

    def _purge_expired(self, now: float):
        expiry = self._expiry
        cache = self.cache
        while expiry:
            key = next(iter(expiry))
            if now <= cache[key].expire_at:
                break
            self._remove_key(key)

    def _remove_key(self, key):
        item = self.cache.pop(key)
        if item.expire_at != INF:
            self._expiry.pop(key, None)
        if self.max_mem_size:
            self.current_size -= item.size

    def __contains__(self, key):
        with self._guard:
            item = self.cache.get(key)
            if item is None:
                return False
            if item.expire_at != INF and monotonic() > item.expire_at:
                self._remove_key(key)
                return False
            return True

    def __len__(self):
        return len(self.cache)

    def refresh_key_ttl(self, key: Any, milliseconds=None):
        """Do refresh of key ttl, if present."""
        ms = milliseconds or self.timeout
        if not ms:
            return
        with self._guard:
            item = self.cache.get(key)
            if item is None:
                return
            item.expire_at = monotonic() + ms / 1000
            self._expiry[key] = None
            self._expiry.move_to_end(key)

    @classmethod
    def get_key(cls, *args, **kwargs):
        """Helper method to generate keys from *args, **kwargs."""
        return _make_key(args, kwargs)

    @classmethod
    def serialize_key(cls, data: Any):
        """Serialize a single argument into its key representation."""
        return _serialize(data)

    def expire(self, *args, **kwargs):
        """Usefull to expire any combination of *args, **kwargs."""
        key = _make_key(args, kwargs)
        with self._guard:
            if key in self.cache:
                self._remove_key(key)


class LRUCache(ExpirableCache):
    """Cache with optional ttl, evicting the least recently used entry when full."""

    _lru = True

    @property
    def access(self):
        """Get accesses as map."""
        return {key: val.access for key, val in self.cache.items()}
