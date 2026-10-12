"""Onecache main module."""

import os
from functools import update_wrapper
from typing import Optional

if os.environ.get("ONECACHE_NO_EXTENSIONS"):
    from onecache._core import CacheValue, ExpirableCache, LRUCache, monotonic

    COMPILED = False
else:
    try:
        from onecache._ccore import CacheValue, ExpirableCache, LRUCache, monotonic

        COMPILED = True
    except ImportError:
        from onecache._core import CacheValue, ExpirableCache, LRUCache, monotonic

        COMPILED = False

__all__ = [
    "AsyncCacheDecorator",
    "CacheDecorator",
    "CacheValue",
    "COMPILED",
    "ExpirableCache",
    "LRUCache",
    "monotonic",
]

_MISSING = object()


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
            * **max_mem_size (int)**: max mem size inside cache structure. default=None which means no limit.
                For pypy this value is ignored as the objects can change by the JIT compilation.
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
        self._fast = type(self.cache) in (ExpirableCache, LRUCache)

    def __call__(self, func):
        cache = self.cache
        skip_args = self.skip_args

        if self._fast:
            return update_wrapper(cache._wrap(func, skip_args), func, updated=())

        def wrapper(*args, **kwargs):
            key = "any" if skip_args else cache.get_key(*args, **kwargs)
            if key not in cache:
                resp = func(*args, **kwargs)
                cache.set(key, resp)
                return resp
            return cache.get(key)

        wrapper.cache = cache

        return update_wrapper(wrapper, func, updated=())


class AsyncCacheDecorator(CacheDecorator):
    """Async Decorator for ExpirableCache"""

    def __call__(self, func):
        cache = self.cache
        skip_args = self.skip_args

        if self._fast:
            make_key = cache._make_key
            lookup = cache._lookup
            set_value = cache.set

            async def async_wrapper(*args, **kwargs):
                key = "any" if skip_args else make_key(args, kwargs)
                value = lookup(key, _MISSING)
                if value is _MISSING:
                    value = await func(*args, **kwargs)
                    set_value(key, value)
                return value

        else:

            async def async_wrapper(*args, **kwargs):
                key = "any" if skip_args else cache.get_key(*args, **kwargs)
                if key not in cache:
                    resp = await func(*args, **kwargs)
                    cache.set(key, resp)
                    return resp
                return cache.get(key)

        async_wrapper.cache = cache

        return update_wrapper(async_wrapper, func, updated=())
