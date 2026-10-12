
[![Coverage Status](https://coveralls.io/repos/github/sonic182/onecache/badge.svg?branch=master)](https://coveralls.io/github/sonic182/onecache?branch=master)
![github status](https://github.com/sonic182/onecache/actions/workflows/python.yml/badge.svg)
# OneCache

Python cache for sync and async code.

Cache uses an LRU algorithm and can optionally set TTLs per entry.

On CPython the cache core is a compiled Cython extension (prebuilt wheels for Linux, macOS and Windows on x86_64 and ARM64). On PyPy, or on platforms without a prebuilt wheel, it falls back to an equivalent pure Python implementation. `onecache.COMPILED` tells which one is in use.

Tested automatically on CPython 3.10 and 3.14 and PyPy 3.11 across Linux, macOS, and Windows on x86_64 and ARM64 (see the workflow badge). Python 3.8 and 3.9 are still installable and get prebuilt wheels, but are no longer part of the test matrix.

# Usage

```python
from onecache import CacheDecorator
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


def test_cache_counter():
    """Test async cache, counter case."""
    counter = Counter()

    @CacheDecorator()
    def sample(counter: Counter):
        counter.count += 1
        return counter.count

    assert 1 == (sample(counter))
    assert 1 == (sample(counter))
```

Decorator classes supports the following arguments

* **maxsize (int)**: Maximun number of items to be cached. default: 512
* **ttl (int)**: time to expire in milliseconds, if None, it does not expire. default: None
* **skip_args (bool)**: apply cache as the function doesn't have any arguments, default: False
* **cache_class (class)**: Class to use for cache instance. default: LRUCache
* **refresh_ttl (bool)**: if cache with ttl, This flag makes key expiration timestamp to be refresh per access. default: False
* **thread_safe (bool)**: tell decorator to use thread safe lock. default=False
* **max_mem_size (int)**: max mem size in bytes, as the sum over every entry of the shallow `sys.getsizeof` of its value, its key and, when the key is a tuple of arguments, each of those arguments. default=None which means no limit. For pypy this value is ignored as the objects can change by the JIT compilation.

If num of records exceds maxsize, it drops the least recently used one. With `max_mem_size`, a value bigger than the limit is not cached.

Use `thread_safe=True` when the decorated function is called from several threads.

Arguments are keyed like `functools.lru_cache` (with `typed=False`) does:

* A single `int` or `str` argument is the key itself; any other call is keyed by the tuple of its arguments and keyword arguments (keyword order doesn't matter). Arguments are compared by hash and equality, so `f(1, 2)`, `f(1.0, 2)` and `f(True, 2)` share an entry, while `f(1)` and `f("1")` don't.
* If a call has a list, dict or set argument, the whole call is keyed by the string form of its arguments, like onecache did before 0.10.0.
* The key holds a reference to the arguments, so the cache keeps them alive (including `self` for decorated methods) until the entry is evicted or expires. Use `ttl`, a smaller `maxsize` or `.cache.clear()` if that matters.

To key every call by strings instead, use a `cache_class` subclass that overrides the `serialize_key` classmethod.

The decorated function exposes its cache as `.cache`: `.cache.expire(*args, **kwargs)` drops one entry, `.cache.clear()` drops all of them, and `.cache.cache` is a read-only view of the entries.

Set `ONECACHE_NO_EXTENSIONS` to any non-empty value to force the pure Python implementation. If the extension failed to build when installing from source (e.g. no compiler), pip may keep reusing that pure Python build from its cache; reinstall with `pip install --no-cache-dir --force-reinstall onecache` after installing a compiler.

# Performance

Compared with `functools.lru_cache` (CPython's C implementation), in nanoseconds per call (lower is better), measured with `benchmarks/compare_lru_cache.py` on CPython 3.12, macOS x86_64, `maxsize=512`:

| Case | lru_cache | onecache (Cython) | Cython vs lru_cache | onecache (pure Python) |
|---|---|---|---|---|
| Hit, 1 positional arg | 88 | 138 | 1.6x slower | 767 |
| Hit, 2 args + 1 kwarg | 234 | 488 | 2.1x slower | 1,592 |
| Miss on a full cache (evicts) | 252 | 462 | 1.8x slower | 1,901 |
| Hit, thread safe | 88 | 180 | 2.1x slower | 788 |
| Hit, with ttl | n/a | 225 | n/a | 1,211 |
| Hit, list argument | n/a | 580 | n/a | 2,239 |

`lru_cache` is still faster: it is built into CPython, while onecache's decorated function goes through a Cython call wrapper and does more bookkeeping per call. In exchange, onecache supports TTLs, async functions, expiring a single entry with `expire()`, a memory limit, and unhashable arguments such as lists and dicts (`lru_cache` raises `TypeError` for them). If you only need a plain LRU cache for hashable arguments, `functools.lru_cache` is the faster choice.

The pure Python column is what PyPy and platforms without a prebuilt wheel use. Numbers depend on the machine; run `python benchmarks/compare_lru_cache.py` (after `make build_ext`) to measure yours.


# Development

Install dependencies with Poetry (includes dev + test groups):
```bash
poetry install --with test,dev
```

Build the Cython extension in place (needed after any change to `onecache/_ccore.pyx`):
```bash
make build_ext
```

Run the test suite against the compiled and the pure Python implementations:
```bash
poetry run pytest
ONECACHE_NO_EXTENSIONS=1 poetry run pytest
```

`onecache/_ccore.pyx` and `onecache/_core.py` implement the same API and must be kept in sync.

# Releasing

Pull requests only build cp310 and cp314 wheels, so first run the `Wheels` workflow by hand on `master` (Actions → Wheels → Run workflow) to build and test every Python version. Then bump `version` in `pyproject.toml` and push a tag with the same value (e.g. `0.9.0`). The `Wheels` workflow builds the wheels with cibuildwheel, the sdist and a pure Python fallback wheel, and publishes them to PyPI through trusted publishing. That needs a `pypi` environment in the GitHub repository settings and a trusted publisher on PyPI for this repository, workflow `wheels.yml` and environment `pypi`.

Lint and format checks:
```bash
poetry run flake8
poetry run autopep8 --in-place --recursive onecache tests
```

# Contribute

1. Fork
2. create a branch `feature/your_feature`
3. commit - push - pull request

Thanks :)
