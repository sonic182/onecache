import copy
import gc
import os
import pickle
import sys
import threading
import weakref
from concurrent.futures import ThreadPoolExecutor
from sys import getsizeof
from time import sleep

import pytest

from onecache import COMPILED, AsyncCacheDecorator, CacheDecorator, CacheValue, ExpirableCache, LRUCache
from onecache.utils import IS_PYPY


def set_expired(key, cache):
    """Dummy helper to expire a cache value."""
    key = cache.get_key(key)
    cache.cache[key].expire_at = -1.0


class Counter:
    def __init__(self, count=0):
        self.count = count


@CacheDecorator()
def module_level_cached(num):
    return num


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

    something(1)
    something(2)
    something(1)
    something(3)
    assert something.cache.cache == {1: CacheValue(1), 3: CacheValue(3)}


def test_decorated_method_and_custom_cache_class():
    """Test methods bind self, and cache_class subclasses keep working."""

    class MyCache(LRUCache):
        pass

    class Doubler:
        def __init__(self, factor):
            self.factor = factor
            self.calls = 0

        @CacheDecorator()
        def compute(self, num):
            self.calls += 1
            return num * self.factor

        @CacheDecorator(cache_class=MyCache)
        def custom(self, num):
            self.calls += 1
            return num + self.factor

    two, three = Doubler(2), Doubler(3)
    assert [two.compute(5), two.compute(5), three.compute(5)] == [10, 10, 15]
    assert [two.custom(1), two.custom(1)] == [3, 3]
    assert (two.calls, three.calls) == (2, 1)
    assert Doubler.compute.__name__ == "compute"
    assert isinstance(Doubler.custom.cache, MyCache)


@pytest.mark.parametrize("thread_safe", [False, True])
def test_argument_keys(thread_safe):
    """Test keys for hashable, unhashable and keyword arguments."""
    calls = Counter()

    class Items(list):
        pass

    @CacheDecorator(thread_safe=thread_safe)
    def something(*args, **kwargs):
        calls.count += 1
        return len(args) + len(kwargs)

    for _ in range(2):
        something(1)
        something("1")
        something([1, 2])
        something({"a": [1]})
        something(1, b=2, c=3)
        something(1, c=3, b=2)
        something((1, [2]))
        something(Items([3]))
    assert calls.count == 7

    something.cache.expire([1, 2])
    something.cache.expire(1, c=3, b=2)
    something.cache.expire((1, [2]))
    something.cache.expire(Items([3]))
    something([1, 2])
    something(1, b=2, c=3)
    something((1, [2]))
    something(Items([3]))
    assert calls.count == 11
    key = something.cache.get_key(1, b=2)
    assert pickle.loads(pickle.dumps(key)) == key

    class Arg:
        pass

    arg = Arg()
    released = weakref.ref(arg)
    something(arg)
    del arg
    gc.collect()
    assert released() is not None
    something.cache.clear()
    gc.collect()
    assert released() is None

    class Clash:
        def __hash__(self):
            return 1

        def __eq__(self, other):
            raise TypeError("cannot compare")

    something(Clash())
    with pytest.raises(TypeError, match="cannot compare"):
        something(Clash())


@pytest.mark.parametrize("options", [{"ttl": 60000}, {"maxsize": 3}, {"max_mem_size": 1024 * 64, "maxsize": 3}])
def test_argument_hash_changes_after_call(options):
    """Test entries are removed even if their argument hash changed or raises after the call."""

    class Unstable:
        def __init__(self, value):
            self.value = value
            self.broken = False

        def __hash__(self):
            if self.broken:
                raise ValueError("unhashable now")
            return hash(self.value)

        def __eq__(self, other):
            return isinstance(other, Unstable) and self.value == other.value

    @CacheDecorator(**options)
    def something(item):
        return item.value

    changed, broken = Unstable(1), Unstable(2)
    something(changed)
    something(broken)
    for item in something.cache.cache.values():
        item.expire_at = -1.0
    changed.value = 10
    broken.broken = True
    assert [something(Unstable(num)) for num in (3, 4, 5)] == [3, 4, 5]
    drops_all = COMPILED and "ttl" not in options and sys.version_info < (3, 14)
    assert len(something.cache) == (2 if drops_all else 3)
    assert something(Unstable(5)) == 5
    assert something.cache.current_size == sum(item.size for item in something.cache.cache.values())

    something.cache.clear()
    stale, kept = Unstable(6), Unstable(7)
    something(stale)
    something(kept)
    something.cache.cache[something.cache.get_key(stale)].expire_at = -1.0
    stale.value = 60
    kept.value = 70
    something(Unstable(8))
    something(Unstable(9))
    assert something(Unstable(70)) == 70

    something(kept)
    kept.value = 700
    assert sum(something.cache.access.values()) <= 1
    something.cache.clear()
    assert len(something.cache) == 0


@pytest.mark.asyncio
async def test_async_argument_keys():
    """Test the async decorator with unhashable and keyword arguments."""
    calls = Counter()

    @AsyncCacheDecorator()
    async def something(items, scale=1):
        calls.count += 1
        return sum(items) * scale

    assert await something([1, 2], scale=2) == 6
    assert await something([1, 2], scale=2) == 6
    assert calls.count == 1


def test_none_result_is_cached():
    """Test None results are cached instead of recomputed."""
    counter = Counter()

    @CacheDecorator()
    def something(num):
        counter.count += 1

    assert something(1) is None
    assert something(1) is None
    assert counter.count == 1


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
    assert something.cache.cache == {2: CacheValue(2), 3: CacheValue(3)}


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
    assert something.cache.access == {2: 0, 3: 0}


def test_lru_and_ttl_refresh():
    """Test refresh ttl cache"""

    @CacheDecorator(ttl=10000, refresh_ttl=True)
    def something(num):
        return num

    something(1)
    something(2)
    first_expiration = something.cache.cache[1].expire_at
    sleep(0.05)
    something(1)
    assert something.cache.cache[1].expire_at > first_expiration

    set_expired(2, something.cache)
    something(3)
    assert something.cache.access == {1: 1, 3: 0}


def test_refresh_key_ttl():
    """Test refresh_key_ttl with a custom ttl, with and without a default ttl."""
    caches = [LRUCache(timeout=10000), LRUCache()]
    for cache in caches:
        cache.set("a", 1)
        cache.set("b", 2)
        cache.refresh_key_ttl("a", 1)
    sleep(0.05)
    for cache in caches:
        assert "a" not in cache
        assert cache.get("b") == 2


def test_custom_key_serialization_and_expire():
    """Test cache_class overriding serialize_key, nested values and expire()."""
    calls = Counter()

    class CounterKeys(LRUCache):
        @classmethod
        def serialize_key(cls, data):
            if isinstance(data, Counter):
                return f"counter{data.count}"
            return super().serialize_key(data)

    @CacheDecorator(cache_class=CounterKeys)
    def something(counters):
        calls.count += 1
        return len(counters)

    something([Counter(1)])
    something([Counter(1)])
    assert list(something.cache.cache) == ["counter1"]
    something.cache.expire([Counter(1)])
    something([Counter(1)])
    assert calls.count == 2


@pytest.mark.parametrize("thread_safe", [False, True])
def test_reentrant_removal_from_finalizer(thread_safe):
    """Test a value finalizer touching the cache while entries are purged."""
    cache = LRUCache(timeout=10000, thread_safe=thread_safe)
    results = []

    class Reenter:
        def __del__(self):
            cache.expire("b")

    def run():
        cache.set("a", Reenter())
        cache.set("b", 1)
        cache.set("c", 2)
        set_expired("a", cache)
        set_expired("b", cache)
        results.append(cache.get("c"))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(5)
    assert not thread.is_alive(), "cache deadlocked"
    assert results == [2]
    assert "a" not in cache
    assert "b" not in cache


def test_edited_expiration_and_non_positive_ttl():
    """Test entries whose expiration is edited by hand, and ttl <= 0 meaning no expiration."""
    cache = ExpirableCache(1, timeout=10000)
    cache.set("a", 1)
    cache.cache["a"].expire_at = float("inf")
    cache.set("b", 2)
    assert cache.get("b") == 2

    for size in (0, -1):
        with pytest.raises(ValueError):
            LRUCache(size)

    for timeout in (0, -5):
        cache = LRUCache(timeout=timeout)
        cache.set("a", 1)
        cache.refresh_key_ttl("a")
        assert cache.get("a") == 1


def test_pickle_and_copy():
    """Test pickling and copying of decorated functions, entries and caches."""
    assert pickle.loads(pickle.dumps(module_level_cached)) is module_level_cached
    assert copy.deepcopy(module_level_cached) is module_level_cached
    assert weakref.ref(module_level_cached)() is module_level_cached

    cache = LRUCache(2000, timeout=10000)
    for num in range(1500):
        cache.set(str(num), num)
    cache.get("7")
    entries = pickle.loads(pickle.dumps(dict(cache.cache)))
    assert entries == dict(cache.cache)
    assert entries["7"].access == 1
    assert entries["7"].expire_at == cache.cache["7"].expire_at
    assert copy.deepcopy(dict(cache.cache)) == dict(cache.cache)

    for action in (pickle.dumps, copy.copy, copy.deepcopy):
        with pytest.raises(TypeError):
            action(cache)


def test_thread_safe_stress():
    """Test concurrent operations keep the cache bounded and its size accounting exact."""
    cache = LRUCache(16, timeout=5, refresh_ttl=True, thread_safe=True, max_mem_size=1 << 20)

    def work(seed):
        for i in range(3000):
            key = str((seed * 7 + i) % 40)
            op = i % 10
            if op < 5:
                cache.get(key)
            elif op < 8:
                cache.set(key, key * (i % 30 + 1))
            elif op == 8:
                cache.expire(key)
            else:
                cache.refresh_key_ttl(key, 10)

    with ThreadPoolExecutor(4) as executor:
        list(executor.map(work, range(4)))

    assert len(cache) <= 16
    if not IS_PYPY:
        expected = sum(getsizeof(key) + getsizeof(val.value) for key, val in cache.cache.items())
        assert cache.current_size == expected


def test_clear_and_read_only_view():
    """Test cache entries are only changed through the cache API."""

    @CacheDecorator(maxsize=2, ttl=10000, max_mem_size=1 << 20)
    def something(num):
        return num

    something(1)
    something(2)
    view = something.cache.cache
    with pytest.raises(TypeError):
        view["3"] = CacheValue(3)
    something.cache.clear()
    assert len(something.cache) == 0
    assert something.cache.current_size == 0

    for num in (3, 4, 5):
        something(num)
    assert view == {4: CacheValue(4), 5: CacheValue(5)}


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

    expected = (getsizeof(random_data[1]) * 2) + (getsizeof(1) + getsizeof(2))

    # key 0 got removed
    assert something.cache.cache == {
        1: CacheValue(random_data[1]),
        2: CacheValue(random_data[2]),
    }
    assert something.cache.current_size == expected

    something.cache.set("big", os.urandom(1024 * 4))
    assert "big" not in something.cache
    assert len(something.cache) == 2

    @CacheDecorator(max_mem_size=1024 * 64)
    def sized(text, num):
        return num

    text = "x" * 10000
    sized(text, 1)
    assert sized.cache.current_size == getsizeof((text, 1)) + getsizeof(text) + 2 * getsizeof(1)
