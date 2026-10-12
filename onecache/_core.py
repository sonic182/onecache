"""Pure Python cache implementation, used on PyPy or when the extension is unavailable."""

from collections import OrderedDict
from contextlib import nullcontext
from sys import getsizeof
from threading import RLock
from time import monotonic
from types import MappingProxyType
from typing import Any, Dict, Optional, Tuple
from weakref import WeakKeyDictionary

from onecache.utils import IS_PYPY

INF = float("inf")
_MISSING = object()


class _Marker:
    __slots__ = ("name",)

    def __init__(self, name: str):
        self.name = name

    def __repr__(self):
        return self.name

    def __reduce__(self):
        return (_marker, (self.name,))


def _marker(name: str) -> _Marker:
    return _KWARGS if name == _KWARGS.name else _UNHASHABLE


_KWARGS = _Marker("<kwargs>")
_UNHASHABLE = _Marker("<unhashable>")
_DEFAULT_KEY_CLASSES: "WeakKeyDictionary[type, bool]" = WeakKeyDictionary()


class CacheValue:
    """Cache entry holding the value, its expiration (monotonic seconds) and access count."""

    __slots__ = ("value", "expire_at", "size", "access")

    def __init__(self, value: Any, expire_at: Optional[float] = None):
        self.value = value
        self.expire_at = INF if expire_at is None else expire_at
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

    def __reduce__(self):
        return (_restore_value, (self.value, self.expire_at, self.size, self.access))


def _restore_value(value, expire_at, size, access):
    item = CacheValue(value, expire_at)
    item.size = size
    item.access = access
    return item


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


def _string_key(args: tuple, kwargs: dict) -> str:
    if not kwargs and len(args) == 1:
        return _serialize(args[0])
    parts = [_serialize(arg) for arg in args]
    if kwargs:
        parts.extend(f"{key}={_serialize(kwargs[key])}" for key in sorted(kwargs))
    return "-".join(parts)


def _make_key(args: tuple, kwargs: dict):
    if not kwargs:
        if len(args) == 1:
            arg = args[0]
            if type(arg) is str or type(arg) is int:
                return arg
        for arg in args:
            if type(arg).__hash__ is None:
                return (_UNHASHABLE, _string_key(args, kwargs))
        key = args
    else:
        for arg in args:
            if type(arg).__hash__ is None:
                return (_UNHASHABLE, _string_key(args, kwargs))
        for value in kwargs.values():
            if type(value).__hash__ is None:
                return (_UNHASHABLE, _string_key(args, kwargs))
        parts = list(args)
        parts.append(_KWARGS)
        for name, value in kwargs.items() if len(kwargs) == 1 else sorted(kwargs.items()):
            parts.append(name)
            parts.append(value)
        key = tuple(parts)
    try:
        hash(key)
    except TypeError:
        return (_UNHASHABLE, _string_key(args, kwargs))
    return key


def _key_size(key) -> int:
    size = getsizeof(key)
    if type(key) is tuple:
        size += sum(getsizeof(part) for part in key)
    return size


def _default_keys(cls) -> bool:
    if cls is ExpirableCache or cls is LRUCache:
        return True
    try:
        return _DEFAULT_KEY_CLASSES[cls]
    except KeyError:
        pass
    result = next(klass for klass in cls.__mro__ if "serialize_key" in vars(klass)) is ExpirableCache
    _DEFAULT_KEY_CLASSES[cls] = result
    return result


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
        self._data: Dict[Any, CacheValue] = OrderedDict()
        self._expiry: Dict[int, Tuple[Any, CacheValue]] = OrderedDict()
        self._timeout = timeout
        self._ttl = timeout / 1000 if timeout and timeout > 0 else None
        if size < 1:
            raise ValueError("size must be at least 1")
        self.size = size
        self._max_mem_size = None if IS_PYPY else max_mem_size
        self._current_size = 0
        self.refresh_ttl = refresh_ttl
        self._thread_safe = bool(thread_safe)
        self._guard = RLock() if thread_safe else nullcontext()

    @property
    def cache(self):
        """Read-only view of the cached entries."""
        return MappingProxyType(self._data)

    @property
    def timeout(self):
        """Ttl in milliseconds, None when entries do not expire."""
        return self._timeout

    @property
    def max_mem_size(self):
        """Max memory size of the cached entries, None when unlimited."""
        return self._max_mem_size

    @property
    def current_size(self):
        """Memory size of the cached entries, tracked only with max_mem_size."""
        return self._current_size

    @property
    def thread_safe(self):
        """Whether cache operations are guarded by a lock."""
        return self._thread_safe

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
        item = self._data.get(key)
        if item is None:
            return default
        if item.expire_at != INF:
            now = monotonic()
            if now > item.expire_at:
                self._remove_entry(key, item)
                return default
            if self.refresh_ttl and self._ttl:
                item.expire_at = now + self._ttl
                try:
                    self._expiry.move_to_end(id(item))
                except KeyError:
                    pass
        if self._lru:
            try:
                self._data.move_to_end(key)
            except KeyError:
                pass
            item.access += 1
        return item.value

    def set(self, key, data):
        """Set value for key, evicting entries if needed.

        With max_mem_size, a value bigger than the limit is not cached.
        """
        with self._guard:
            self._set_unlocked(key, data)

    def _set_unlocked(self, key, data):
        now = monotonic() if self._ttl or self._expiry else 0.0
        if self._expiry:
            self._purge_expired(now)
        size = 0
        if self._max_mem_size:
            size = _key_size(key) + getsizeof(data)
            if size > self._max_mem_size:
                current = self._data.get(key)
                if current is not None:
                    self._remove_entry(key, current)
                return
        current = self._data.get(key)
        if current is not None:
            self._remove_entry(key, current)
        elif self._data and len(self._data) >= self.size:
            self._evict_oldest()

        item = CacheValue(data)
        if self._max_mem_size:
            item.size = size
            while self._data and self._current_size + size > self._max_mem_size:
                self._evict_oldest()
            self._current_size += size
        self._data[key] = item
        if self._ttl:
            item.expire_at = now + self._ttl
            self._expiry[id(item)] = (key, item)

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

    def _make_key(self, args: tuple, kwargs: dict):
        return _make_key(args, kwargs)

    def _purge_expired(self, now: float):
        expiry = self._expiry
        while expiry:
            key, item = expiry[next(iter(expiry))]
            if now <= item.expire_at:
                break
            self._remove_entry(key, item)

    def _evict_oldest(self):
        item = self._data.popitem(last=False)[1]
        self._forget(item)

    def _remove_entry(self, key, item: CacheValue):
        try:
            found = self._data.get(key) is item
        except Exception:
            found = False
        if found:
            del self._data[key]
            self._forget(item)
            return
        entry = self._expiry.get(id(item))
        if entry is not None and entry[1] is item:
            self._drop_all()

    def _forget(self, item: CacheValue):
        if self._expiry:
            self._expiry.pop(id(item), None)
        if self._max_mem_size:
            self._current_size -= item.size

    def _drop_all(self):
        entries = list(dict.values(self._data))
        self._data.clear()
        self._expiry.clear()
        self._current_size = 0
        return entries

    def __contains__(self, key):
        with self._guard:
            item = self._data.get(key)
            if item is None:
                return False
            if item.expire_at != INF and monotonic() > item.expire_at:
                self._remove_entry(key, item)
                return False
            return True

    def __len__(self):
        return len(self._data)

    def __reduce__(self):
        raise TypeError(f"cannot pickle {type(self).__name__!r} object")

    def clear(self):
        """Remove every entry."""
        with self._guard:
            entries = self._drop_all()
        entries.clear()

    def refresh_key_ttl(self, key: Any, milliseconds=None):
        """Do refresh of key ttl, if present."""
        ms = milliseconds or (self._timeout if self._ttl else None)
        if not ms:
            return
        with self._guard:
            item = self._data.get(key)
            if item is None:
                return
            item.expire_at = monotonic() + ms / 1000
            self._expiry[id(item)] = (key, item)
            self._expiry.move_to_end(id(item))

    @classmethod
    def get_key(cls, *args, **kwargs):
        """Helper method to generate keys from *args, **kwargs."""
        if _default_keys(cls):
            return _make_key(args, kwargs)
        serialize = cls.serialize_key
        kwargs_list = [f"{key}={serialize(kwargs[key])}" for key in sorted(kwargs)]
        return "-".join([serialize(item) for item in list(args) + kwargs_list])

    @classmethod
    def serialize_key(cls, data: Any):
        """Serialize a single argument into a string key.

        Overriding it in a subclass makes the cache use string keys built with it. Whether a class
        overrides it is checked once per class.
        """
        if type(data) is str:
            return data
        if isinstance(data, dict):
            return ",".join([f"{key}={cls.serialize_key(val)}" for key, val in data.items()])
        if isinstance(data, list):
            return ",".join([cls.serialize_key(val) for val in data])
        if isinstance(data, str):
            return data
        return str(data)

    def expire(self, *args, **kwargs):
        """Usefull to expire any combination of *args, **kwargs."""
        key = self.get_key(*args, **kwargs)
        with self._guard:
            item = self._data.get(key)
            if item is not None:
                self._remove_entry(key, item)


class LRUCache(ExpirableCache):
    """Cache with optional ttl, evicting the least recently used entry when full."""

    _lru = True

    @property
    def access(self):
        """Get accesses as map."""
        with self._guard:
            return {key: val.access for key, val in dict.items(self._data)}
