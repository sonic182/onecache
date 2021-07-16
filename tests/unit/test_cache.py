import asyncio

import pytest

from onecache import AsyncCacheDecorator


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


@pytest.mark.asyncio
async def test_async_cache_ttl():
    """Test async cache, ttl case."""
    counter = Counter()

    @AsyncCacheDecorator(ttl=200)  # 200 ms
    async def mycoro(counter: Counter):
        counter.count += 1
        return counter.count

    assert 1 == (await mycoro(counter))
    assert 1 == (await mycoro(counter))
    await asyncio.sleep(0.3)  # 300ms
    assert 2 == (await mycoro(counter))


@pytest.mark.asyncio
async def test_expire_cache():
    """Test async cache, ttl case."""
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
