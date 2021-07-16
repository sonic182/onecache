from datetime import datetime, timedelta
from typing import Any, Optional


class ExpirableCache(object):
    """
    Class used for custom cache decorator, dummy expirable cache based
    on dict structure.

    Params:
        * **size**: max items in dict.
        * **timeout**: Timeout in milliseconds, if it is None,
            there is no timeout.
    """

    def __init__(self, size=512, timeout=None):
        self.cache = {}
        self.timeout = timeout
        self.size = size

    def set(self, key, data):
        if self.timeout:
            expire_at = datetime.utcnow() + timedelta(milliseconds=self.timeout)
            self.cache[key] = {"value": data, "expire_at": expire_at}
        else:
            self.cache[key] = data

        if len(self.cache) > self.size:
            self.cache.pop(next(iter(self.cache)))

    def get(self, key):
        self._check_expired(key)
        data = self.cache.get(key)
        if self.timeout and data:  # if ttl, return value
            return data["value"]
        return data

    def _check_expired(self, key):
        if self.timeout and key in self.cache:
            data = self.cache[key]
            if datetime.utcnow() > data["expire_at"]:
                del self.cache[key]
                data = None

    def __contains__(self, key):
        self._check_expired(key)
        return key in self.cache

    def __len__(self):
        return len(self.cache)

    @classmethod
    def get_key(cls, *args, **kwargs):
        """Helper method to generate keys from *args, **kwargs."""
        kwargs_list = [f"{key}={cls.serialize_key(val)}" for key, val in kwargs.items()]
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
            del self.cache[key]


# Decorator!
class CacheDecorator:
    """Decorator for ExpirableCache"""

    def __init__(self, maxsize=512, ttl: Optional[int] = None, skip_args: bool = False):
        """
        Args:
            * maxsize: Maximun size of cache. default=512
            * ttl: time to expire in milliseconds, if None, it does not expire. default=None
        """
        self.cache = ExpirableCache(maxsize, ttl)
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
