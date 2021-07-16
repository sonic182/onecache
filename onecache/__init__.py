from collections import OrderedDict
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
        self.cache = OrderedDict()
        self.timeout = timeout
        self.size = size

    def set(self, key, data):
        if len(self.cache) + 1 > self.size:
            self._pop_one()

        if self.timeout:
            expire_at = datetime.utcnow() + timedelta(milliseconds=self.timeout)
            self.cache[key] = {"value": data, "expire_at": expire_at}
        else:
            self.cache[key] = data

    def _pop_one(self):
        self.cache.pop(next(iter(self.cache)))

    def get(self, key):
        self._check_expired(key)
        data = self.cache.get(key)
        if self.timeout and data:  # if ttl, return value
            return data["value"]
        return data

    def _check_expired(self, key):
        to_rm = []
        if self.timeout:
            for key, data in self.cache.items():
                if datetime.utcnow() > data["expire_at"]:
                    to_rm.append(key)
        for key in to_rm:
            self._remove_key(key)

    def _remove_key(self, key):
        del self.cache[key]

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
            self._remove_key(key)


class LRUCache(ExpirableCache):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.access = {}

    def get(self, key):
        self._check_expired(key)
        if key in self.cache:
            self._increment(key)
        return super().get(key)

    def set(self, key, val):
        self.access[key] = 0
        return super().set(key, val)

    def _increment(self, key):
        self.access[key] = self.access.get(key, 0) + 1

    def _pop_one(self):
        ordered_cache = sorted(
            map(
                lambda item: (item[0], item[1], self.access[item[0]]),
                self.cache.items(),
            ),
            key=lambda item: item[2],
        )
        del self.access[ordered_cache[0][0]]
        del self.cache[ordered_cache[0][0]]

    def _remove_key(self, key):
        super()._remove_key(key)
        del self.access[key]


# Decorator!
class CacheDecorator:
    """Decorator for ExpirableCache"""

    def __init__(
        self,
        maxsize=512,
        ttl: Optional[int] = None,
        skip_args: bool = False,
        cache_class=LRUCache,
    ):
        """
        Args:
            * maxsize (int): Maximun size of cache. default: 512
            * ttl (int): time to expire in milliseconds, if None, it does not expire. default: None
            * skip_args (bool): apply cache as the function doesn't have any arguments, default: False
        """
        self.cache = cache_class(maxsize, ttl)
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
