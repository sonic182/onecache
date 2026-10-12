# cython: language_level=3, boundscheck=False, wraparound=False, initializedcheck=False, embedsignature=True
"""Compiled cache implementation, API compatible with onecache._core."""

from cpython.pythread cimport (
    NOWAIT_LOCK,
    WAIT_LOCK,
    PyThread_acquire_lock,
    PyThread_allocate_lock,
    PyThread_free_lock,
    PyThread_release_lock,
    PyThread_type_lock,
)

from sys import getsizeof
from types import MappingProxyType, MethodType


cdef extern from *:
    """
    #ifdef _WIN32
    #ifndef WIN32_LEAN_AND_MEAN
    #define WIN32_LEAN_AND_MEAN
    #endif
    #include <windows.h>
    static double onecache_monotonic(void) {
        static double inv_freq = 0.0;
        LARGE_INTEGER counter;
        if (inv_freq == 0.0) {
            LARGE_INTEGER freq;
            QueryPerformanceFrequency(&freq);
            inv_freq = 1.0 / (double)freq.QuadPart;
        }
        QueryPerformanceCounter(&counter);
        return (double)counter.QuadPart * inv_freq;
    }
    #else
    #include <time.h>
    static double onecache_monotonic(void) {
        struct timespec ts;
        clock_gettime(CLOCK_MONOTONIC, &ts);
        return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
    }
    #endif
    """
    double onecache_monotonic() nogil


cdef double INF = float("inf")
cdef object _MISSING = object()


def monotonic():
    """Clock used for entry expiration, in seconds."""
    return onecache_monotonic()


cdef class CacheValue:
    """Cache entry holding the value, its expiration (monotonic seconds) and access count."""

    cdef public object value
    cdef public double expire_at
    cdef public Py_ssize_t size
    cdef public Py_ssize_t access
    cdef object key
    cdef CacheValue prev, next
    cdef CacheValue eprev, enext

    def __init__(self, value, expire_at=None):
        self.value = value
        self.expire_at = INF if expire_at is None else expire_at

    def expired(self, now=None):
        """Check if value is expired."""
        return (onecache_monotonic() if now is None else <double>now) > self.expire_at

    def __eq__(self, other):
        if not isinstance(other, CacheValue):
            return NotImplemented
        return self.value == (<CacheValue>other).value

    __hash__ = None


cdef inline CacheValue _new_node(object key, object value):
    cdef CacheValue node = CacheValue.__new__(CacheValue)
    node.key = key
    node.value = value
    node.expire_at = INF
    return node


cdef inline void _link_last(CacheValue root, CacheValue node):
    node.prev = root.prev
    node.next = root
    root.prev.next = node
    root.prev = node


cdef inline void _unlink(CacheValue node):
    node.prev.next = node.next
    node.next.prev = node.prev
    node.prev = None
    node.next = None


cdef inline void _elink_last(CacheValue root, CacheValue node):
    node.eprev = root.eprev
    node.enext = root
    root.eprev.enext = node
    root.eprev = node


cdef inline void _eunlink(CacheValue node):
    node.eprev.enext = node.enext
    node.enext.eprev = node.eprev
    node.eprev = None
    node.enext = None


cdef object _serialize(object data):
    if type(data) is str:
        return data
    if isinstance(data, dict):
        return ",".join([f"{key}={_serialize(val)}" for key, val in data.items()])
    if isinstance(data, list):
        return ",".join([_serialize(val) for val in data])
    if isinstance(data, str):
        return data
    return str(data)


cdef object _make_key(tuple args, dict kwargs):
    cdef list parts
    if not kwargs and len(args) == 1:
        return _serialize(args[0])
    parts = [_serialize(arg) for arg in args]
    if kwargs:
        for key in sorted(kwargs):
            parts.append(f"{key}={_serialize(kwargs[key])}")
    return "-".join(parts)


cdef class ExpirableCache:
    """Cache with optional ttl, evicting the oldest inserted entry when full.

    Params:
        * **size (int)**: max items in dict. default=512
        * **timeout (int)**: Timeout in milliseconds, if it is None,
            there is no timeout. default=None
        * **refresh_ttl (int)**: Refresh ttl anytime key is accessed. default=False
        * **thread_safe (bool)**: Tell cache decorator to be thread safe. default=False
        * **max_mem_size (int)**: max mem size inside cache structure. default=None which means no limit.
    """

    cdef dict _data
    cdef readonly object timeout
    cdef public Py_ssize_t size
    cdef readonly object max_mem_size
    cdef readonly Py_ssize_t current_size
    cdef public bint refresh_ttl
    cdef readonly bint thread_safe
    cdef PyThread_type_lock _lock
    cdef double _ttl
    cdef Py_ssize_t _max_mem
    cdef bint _lru
    cdef CacheValue _root
    cdef CacheValue _eroot
    cdef Py_ssize_t _ecount

    def __cinit__(self, *args, **kwargs):
        self._data = {}
        self._root = CacheValue.__new__(CacheValue)
        self._root.prev = self._root
        self._root.next = self._root
        self._eroot = CacheValue.__new__(CacheValue)
        self._eroot.eprev = self._eroot
        self._eroot.enext = self._eroot

    def __init__(
        self,
        size=512,
        timeout=None,
        refresh_ttl=False,
        thread_safe=False,
        max_mem_size=None,
    ):
        self.timeout = timeout
        self._ttl = timeout / 1000.0 if timeout else 0.0
        self.size = size
        self.max_mem_size = max_mem_size
        self._max_mem = int(max_mem_size) if max_mem_size else 0
        self.refresh_ttl = refresh_ttl
        self.thread_safe = thread_safe
        if thread_safe and self._lock is NULL:
            self._lock = PyThread_allocate_lock()
            if self._lock is NULL:
                raise MemoryError()

    def __dealloc__(self):
        if self._lock is not NULL:
            PyThread_free_lock(self._lock)

    cdef inline int _acquire(self) except -1:
        if self._lock is not NULL and not PyThread_acquire_lock(self._lock, NOWAIT_LOCK):
            with nogil:
                PyThread_acquire_lock(self._lock, WAIT_LOCK)
        return 0

    cdef inline void _release(self):
        if self._lock is not NULL:
            PyThread_release_lock(self._lock)

    @property
    def cache(self):
        """Read-only view of the cached entries."""
        return MappingProxyType(self._data)

    def get(self, key):
        """Get value of key, None if missing or expired."""
        return self._locked_lookup(key, None)

    def _lookup(self, key, default=None):
        return self._locked_lookup(key, default)

    def set(self, key, data):
        """Set value for key, evicting entries if needed.

        With max_mem_size, a value bigger than the limit is not cached.
        """
        self._acquire()
        try:
            self._set(key, data)
        finally:
            self._release()

    def _make_key(self, tuple args, dict kwargs):
        return _make_key(args, kwargs)

    def _wrap(self, func, bint skip_args=False):
        cdef CachedFunction wrapper = CachedFunction.__new__(CachedFunction)
        wrapper.cache = self
        wrapper.func = func
        wrapper.skip_args = skip_args
        return wrapper

    cdef object _locked_lookup(self, object key, object default):
        self._acquire()
        try:
            return self._lookup_unlocked(key, default)
        finally:
            self._release()

    cdef object _lookup_unlocked(self, object key, object default):
        cdef double now = 0.0
        cdef CacheValue item
        if self._ecount:
            now = onecache_monotonic()
            self._purge_expired(now)
        obj = self._data.get(key)
        if obj is None:
            return default
        item = <CacheValue>obj
        if item.expire_at != INF:
            if now == 0.0:
                now = onecache_monotonic()
            if now > item.expire_at:
                self._remove(item)
                return default
            if self.refresh_ttl and self._ttl > 0.0:
                item.expire_at = now + self._ttl
                _eunlink(item)
                _elink_last(self._eroot, item)
        if self._lru:
            _unlink(item)
            _link_last(self._root, item)
            item.access += 1
        return item.value

    cdef int _set(self, object key, object data) except -1:
        cdef double now = 0.0
        cdef Py_ssize_t size = 0
        cdef CacheValue item
        if self._ttl > 0.0 or self._ecount:
            now = onecache_monotonic()
        if self._ecount:
            self._purge_expired(now)
        obj = self._data.get(key)
        if self._max_mem:
            size = getsizeof(key) + getsizeof(data)
            if size > self._max_mem:
                if obj is not None:
                    self._remove(<CacheValue>obj)
                return 0
        if obj is not None:
            self._remove(<CacheValue>obj)
        elif self._data and len(self._data) >= self.size:
            self._remove(self._root.next)

        item = _new_node(key, data)
        if self._max_mem:
            item.size = size
            while self._data and self.current_size + size > self._max_mem:
                self._remove(self._root.next)
            self.current_size += size
        self._data[key] = item
        _link_last(self._root, item)
        if self._ttl > 0.0:
            item.expire_at = now + self._ttl
            _elink_last(self._eroot, item)
            self._ecount += 1
        return 0

    cdef int _purge_expired(self, double now) except -1:
        cdef CacheValue node = self._eroot.enext
        cdef CacheValue nxt
        while node is not self._eroot and now > node.expire_at:
            nxt = node.enext
            self._remove(node)
            node = nxt
        return 0

    cdef int _remove(self, CacheValue item) except -1:
        del self._data[item.key]
        _unlink(item)
        if item.enext is not None:
            _eunlink(item)
            self._ecount -= 1
        if self._max_mem:
            self.current_size -= item.size
        return 0

    def __contains__(self, key):
        self._acquire()
        try:
            return self._contains(key)
        finally:
            self._release()

    cdef bint _contains(self, object key) except -1:
        cdef CacheValue item
        obj = self._data.get(key)
        if obj is None:
            return False
        item = <CacheValue>obj
        if item.expire_at != INF and onecache_monotonic() > item.expire_at:
            self._remove(item)
            return False
        return True

    def __len__(self):
        return len(self._data)

    def clear(self):
        """Remove every entry."""
        cdef CacheValue node
        cdef CacheValue nxt
        cdef dict data
        self._acquire()
        try:
            data = self._data
            node = self._root.next
            while node is not self._root:
                nxt = node.next
                node.prev = node.next = node.eprev = node.enext = None
                node = nxt
            self._data = {}
            self._root.prev = self._root.next = self._root
            self._eroot.eprev = self._eroot.enext = self._eroot
            self._ecount = 0
            self.current_size = 0
        finally:
            self._release()
        data.clear()

    def refresh_key_ttl(self, key, milliseconds=None):
        """Do refresh of key ttl, if present."""
        ms = milliseconds or self.timeout
        if not ms:
            return
        self._acquire()
        try:
            self._refresh(key, ms)
        finally:
            self._release()

    cdef int _refresh(self, object key, object ms) except -1:
        cdef CacheValue item
        obj = self._data.get(key)
        if obj is None:
            return 0
        item = <CacheValue>obj
        item.expire_at = onecache_monotonic() + ms / 1000.0
        if item.enext is not None:
            _eunlink(item)
        else:
            self._ecount += 1
        _elink_last(self._eroot, item)
        return 0

    @classmethod
    def get_key(cls, *args, **kwargs):
        """Helper method to generate keys from *args, **kwargs."""
        serialize = cls.serialize_key
        kwargs_list = [f"{key}={serialize(kwargs[key])}" for key in sorted(kwargs)]
        return "-".join([serialize(item) for item in list(args) + kwargs_list])

    @classmethod
    def serialize_key(cls, data):
        """Serialize a single argument into its key representation."""
        return _serialize(data)

    def expire(self, *args, **kwargs):
        """Usefull to expire any combination of *args, **kwargs."""
        key = self.get_key(*args, **kwargs)
        self._acquire()
        try:
            self._expire(key)
        finally:
            self._release()

    cdef int _expire(self, object key) except -1:
        obj = self._data.get(key)
        if obj is not None:
            self._remove(<CacheValue>obj)
        return 0


cdef class LRUCache(ExpirableCache):
    """Cache with optional ttl, evicting the least recently used entry when full."""

    def __cinit__(self, *args, **kwargs):
        self._lru = True

    @property
    def access(self):
        """Get accesses as map."""
        return {key: (<CacheValue>val).access for key, val in self._data.items()}


cdef class CachedFunction:
    """Callable returned by CacheDecorator when using the builtin cache classes."""

    cdef readonly ExpirableCache cache
    cdef object func
    cdef bint skip_args
    cdef dict __dict__

    def __call__(self, *args, **kwargs):
        cdef ExpirableCache cache = self.cache
        key = "any" if self.skip_args else _make_key(args, kwargs)
        value = cache._locked_lookup(key, _MISSING)
        if value is _MISSING:
            value = self.func(*args, **kwargs)
            cache.set(key, value)
        return value

    def __get__(self, obj, objtype):
        if obj is None:
            return self
        return MethodType(self, obj)
