import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from sys import getsizeof
from time import sleep

import pytest

from onecache import AsyncCacheDecorator, CacheDecorator, CacheValue, ExpirableCache
from onecache.utils import IS_PYPY, utcnow


def set_expired(key, cache):
    """Dummy helper to expire a cache value."""
    key = cache.serialize_key(key)
    val = cache.cache[key]
    val.set_expired(utcnow() - timedelta(seconds=1))


class Counter:
    def __init__(self, count=0):
        self.count = count


@pytest.mark.asyncio
async def test_async_cache_counter():
    """Test async cache, counter case."""
    counter = Counter()

    @AsyncCacheDecorator()
    async def mycoro(counter: Counter):
        counter.count += 1
        return counter.count

    assert 1 == (await mycoro(counter))
    assert 1 == (await mycoro(counter))


def test_cache_counter():
    """Test sync cache, counter case."""
    counter = Counter()

    @CacheDecorator()
    def mycoro(counter: Counter):
        counter.count += 1
        return counter.count

    assert 1 == (mycoro(counter))
    assert 1 == (mycoro(counter))


def test_cache_counter_thread_safe():
    """Test sync cache, counter case."""
    counter = Counter()

    @CacheDecorator(thread_safe=True)
    def mycoro(counter: Counter):
        counter.count += 1
        return counter.count

    with ThreadPoolExecutor(3) as executor:
        futures = []
        latest = 0
        for _ in range(100):
            futures.append(executor.submit(mycoro, counter))

        for fut in futures:
            latest = fut.result()
    assert latest == 1


@pytest.mark.asyncio
async def test_async_cache_ttl():
    """Test async cache, ttl case."""
    counter = Counter()

    @AsyncCacheDecorator(ttl=200)  # 200 ms
    async def mycoro(counter: Counter):
        counter.count += 1
        return counter.count

    assert 1 == (await mycoro(counter))
    set_expired(counter, mycoro.cache)
    assert 2 == (await mycoro(counter))


@pytest.mark.asyncio
async def test_expire_cache():
    """Test async cache, expired ttl case."""
    counter = Counter()

    @AsyncCacheDecorator()
    async def mycoro(counter: Counter):
        counter.count += 1
        return counter.count

    assert 1 == (await mycoro(counter))
    mycoro.cache.expire(counter)
    assert 2 == (await mycoro(counter))


@pytest.mark.asyncio
async def test_cache_size_cleanup():
    """Test async cache, max size cleanup case."""

    @AsyncCacheDecorator(10)
    async def mycoro(counter: Counter):
        counter.count += 1
        return counter.count

    first = Counter(89)
    counters = []  # avoid gc.collect by keeping counters in this list
    assert 90 == (await mycoro(first))
    for _ in range(11):
        counter = Counter()
        counters.append(counter)
        assert 1 == (await mycoro(counter))
    assert 91 == (await mycoro(first))


@pytest.mark.asyncio
async def test_maxsize_cache():
    """Test async cache, max size case."""

    @AsyncCacheDecorator(10)
    async def mycoro(counter: Counter):
        counter.count += 1
        return counter.count

    first = Counter(89)
    counters = []  # avoid gc.collect by keeping counters in this list
    assert 90 == (await mycoro(first))
    for _ in range(11):
        counter = Counter()
        counters.append(counter)
        assert 1 == (await mycoro(counter))
    assert 91 == (await mycoro(first))


def test_maxsize_expirable_cache():
    """Test max size expirable cache."""
    cache = ExpirableCache(2)
    cache.set("foo", "something")
    cache.set("bar", "something")
    cache.set("baz", "something")
    assert cache.cache == {
        "bar": CacheValue("something"),
        "baz": CacheValue("something"),
    }


def test_lru():
    """Test simple lru."""

    @CacheDecorator(maxsize=2)
    def something(num):
        return num

    for _ in range(4):
        something(1)

    for _ in range(3):
        something(2)

    something(3)
    assert something.cache.cache == {"1": CacheValue(1), "3": CacheValue(3)}


def test_ttl():
    """Test lru and ttl cache in conjuntion."""

    @CacheDecorator(ttl=200, cache_class=ExpirableCache)
    def something(num):
        return num

    something(1)
    something(1)
    something(2)
    set_expired(1, something.cache)
    something(3)

    # ttl will expire the most recently used (1)
    assert something.cache.cache == {"2": CacheValue(2), "3": CacheValue(3)}


def test_lru_and_ttl():
    """Test lru and ttl cache in conjuntion."""

    @CacheDecorator(maxsize=2, ttl=200)
    def something(num):
        return num

    something(1)
    something(1)
    something(2)
    set_expired(1, something.cache)
    something(3)

    # ttl will expire the most recently used (1)
    assert something.cache.access == {"2": 0, "3": 0}


def test_lru_and_ttl_refresh():
    """Test refresh ttl cache"""

    @CacheDecorator(maxsize=2, ttl=300, refresh_ttl=True)
    def something(num):
        return num

    something(1)
    something(1)
    sleep(1.5 / 10)
    something(1)
    something(2)
    sleep(1.5 / 10)
    something(3)

    # ttl will expire the most recently used (1)
    assert something.cache.access == {"1": 2, "3": 0}


def test_serialize():
    """Test serialize of args and kwargs in decorator."""
    cache = ExpirableCache()
    assert cache.serialize_key({"foo": "bar"}) == "foo=bar"
    assert cache.serialize_key(["foo", "bar"]) == "foo,bar"
    assert cache.serialize_key("foo") == "foo"


def test_lru_max_mem_size():
    """Test simple lru."""
    if IS_PYPY:
        pytest.skip("unsupported interpreter")
    # max 3KiB
    random_data = []

    @CacheDecorator(maxsize=2, max_mem_size=1024 * 3)
    def something(num):
        res = os.urandom(1025)
        random_data.append(res)
        return res

    for i in range(3):
        something(i)

    expected = (getsizeof(random_data[1]) * 2) + (getsizeof("1") + getsizeof("2"))

    # key "0" got removed
    assert something.cache.cache == {
        "1": CacheValue(random_data[1]),
        "2": CacheValue(random_data[2]),
    }
    assert something.cache.current_size == expected
