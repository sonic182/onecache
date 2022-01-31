from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime, timedelta
from sys import getsizeof
from threading import Lock
from typing import Any, Dict, Optional

from onecache.cache_value import CacheValue


class ExpirableCache(object):
    """
    Class used for custom cache decorator, dummy expirable cache based
    on dict structure.

    Params:
        * **size (int)**: max items in dict. default=512
        * **timeout (int)**: Timeout in milliseconds, if it is None,
            there is no timeout. default=None
        * **refresh_ttl (int)**: Refresh ttl anytime key is accessed. default=False
        * **thread_safe (bool)**: Tell cache decorator to be thread safe. default=False
        * **max_mem_size (int)**: max mem size inside cache structure. default=None which means no limit
    """

    def __init__(
        self,
        size: int = 512,
        timeout: int = None,
        refresh_ttl=False,
        thread_safe=False,
        max_mem_size: int = None,
    ):
        self.cache: Dict[str, CacheValue] = OrderedDict()
        self.timeout = timeout
        self.size = size
        self.max_mem_size = max_mem_size
        self.current_size = 0
        self.refresh_ttl = refresh_ttl
        self.lock = None
        if thread_safe:
            self.lock = Lock()

    def set(self, key, data):
        key_size = getsizeof(key)
        value = None
        with self._scoped():
            if len(self.cache) + 1 > self.size and key not in self.cache:
                self._pop_one()

            if self.timeout:
                expire_at = datetime.utcnow() + timedelta(milliseconds=self.timeout)
                value = CacheValue(data, expire_at)
            else:
                value = CacheValue(data)

            if self.max_mem_size:
                # pop data if it will exceed max mem size
                while (
                    self.current_size + key_size + value.size > self.max_mem_size
                    and len(self.cache) > 1
                ):
                    self._pop_one()
            self.cache[key] = value

            if self.max_mem_size:
                self.current_size += key_size + value.size

    def _pop_one(self):
        key = next(iter(self.cache))
        self._remove_key(key)

    def get(self, key, fetch_value=True):
        self._check_expired(key)
        cache_value = self.cache.get(key)
        if cache_value:
            if self.refresh_ttl:
                with self._scoped():
                    self.refresh_key_ttl(key)
            if fetch_value:
                return cache_value.value
            return cache_value

    def _check_expired(self, key):
        to_rm = []
        if self.timeout:
            for key, cache_value in self.cache.items():
                if cache_value.expired():
                    to_rm.append(key)
        for key in to_rm:
            self._remove_key(key)

    def _remove_key(self, key):
        item = self.cache[key]
        key_size = getsizeof(key)
        if self.max_mem_size:
            self.current_size -= item.size + key_size

        del self.cache[key]

    def __contains__(self, key):
        self._check_expired(key)
        return key in self.cache

    def refresh_key_ttl(self, key: Any, milliseconds=None):
        """Do refresh of key ttl, if present."""
        cache_value = self.cache.get(key)
        if cache_value and (milliseconds or self.timeout):
            ms = milliseconds if milliseconds else self.timeout
            expire_at = datetime.utcnow() + timedelta(milliseconds=ms)
            cache_value.refresh_ttl(expire_at)

    @classmethod
    def get_key(cls, *args, **kwargs):
        """Helper method to generate keys from *args, **kwargs."""
        sorted_kwargs = sorted(kwargs.items(), key=lambda item: item[0])
        kwargs_list = [f"{key}={cls.serialize_key(val)}" for key, val in sorted_kwargs]
        items = list(args) + kwargs_list
        return "-".join([cls.serialize_key(item) for item in items])

    @classmethod
    def serialize_key(cls, data: Any):
        if isinstance(data, dict):
            return ",".join(
                [f"{key}={cls.serialize_key(val)}" for key, val in data.items()]
            )
        elif isinstance(data, list):
            return ",".join([cls.serialize_key(val) for val in data])
        elif isinstance(data, str):
            return data
        else:
            return str(data)

    def expire(self, *args, **kwargs):
        """Usefull to expire any combination of *args, **kwargs."""
        key = self.get_key(*args, **kwargs)
        if key in self.cache:
            self._remove_key(key)

    @contextmanager
    def _scoped(self):
        if self.lock:
            with self.lock:
                yield
        else:
            yield


class LRUCache(ExpirableCache):
    def get(self, key):
        cache_value = super().get(key, fetch_value=False)
        if cache_value:
            with self._scoped():
                self._increment(cache_value)
        return cache_value.value

    def _increment(self, val: CacheValue):
        val.increment()

    def _pop_one(self):
        ordered_cache = sorted(self.cache.items(), key=lambda item: item[1].access)
        key, _ = ordered_cache[0]
        self._remove_key(key)

    @property
    def access(self):
        """Get accesses as map."""
        return {key: val.access for key, val in self.cache.items()}


# Decorator!
class CacheDecorator:
    """Decorator for ExpirableCache"""

    def __init__(
        self,
        maxsize=512,
        ttl: Optional[int] = None,
        skip_args: bool = False,
        cache_class=LRUCache,
        refresh_ttl: Optional[bool] = False,
        thread_safe: Optional[bool] = False,
        max_mem_size: Optional[int] = None,
    ):
        """
        Args:
            * **maxsize (int)**: Maximun number of items to be cached. default: 512
            * **ttl (int)**: time to expire in milliseconds, if None, it does not expire. default: None
            * **skip_args (bool)**: apply cache as the function doesn't have any arguments, default: False
            * **cache_class (class)**: Class to use for cache instance. default: LRUCache
            * **refresh_ttl (bool)**: if cache with ttl, This flag makes key expiration timestamp to be
                refresh per access. default: False
            * **thread_safe (bool)**: tell decorator to use thread safe lock. default=False
            * **max_mem_size (int)**: max mem size in bytes. Ceil for sum of cache values sizes. default=None which means no limit
        """
        self.cache = cache_class(
            maxsize,
            ttl,
            refresh_ttl=refresh_ttl,
            thread_safe=thread_safe,
            max_mem_size=max_mem_size,
        )
        self.maxsize = maxsize
        self.skip_args = skip_args

    def __call__(self, func):
        def wrapper(*args, **kwargs):
            key = "any" if self.skip_args else self.cache.get_key(*args, **kwargs)

            if key not in self.cache:
                resp = func(*args, **kwargs)
                self.cache.set(key, resp)
                return resp
            else:
                return self.cache.get(key)

        wrapper.cache = self.cache

        return wrapper


class AsyncCacheDecorator(CacheDecorator):
    """Async Decorator for ExpirableCache"""

    def __call__(self, func):
        async def async_wrapper(*args, **kwargs):
            key = "any" if self.skip_args else self.cache.get_key(*args, **kwargs)

            if key not in self.cache:
                resp = await func(*args, **kwargs)
                self.cache.set(key, resp)
                return resp
            else:
                return self.cache.get(key)

        async_wrapper.cache = self.cache

        return async_wrapper
