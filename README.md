
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
* **max_mem_size (int)**: max mem size in bytes. Ceil for sum of cache values sizes. default=None which means no limit. For pypy this value is ignored as the objects can change by the JIT compilation.

If num of records exceds maxsize, it drops the least recently used one. With `max_mem_size`, a value bigger than the limit is not cached.

Use `thread_safe=True` when the decorated function is called from several threads.

The decorated function exposes its cache as `.cache`: `.cache.expire(*args, **kwargs)` drops one entry, `.cache.clear()` drops all of them, and `.cache.cache` is a read-only view of the entries.

Set `ONECACHE_NO_EXTENSIONS=1` to force the pure Python implementation. If the extension failed to build when installing from source (e.g. no compiler), pip may keep reusing that pure Python build from its cache; reinstall with `pip install --no-cache-dir --force-reinstall onecache` after installing a compiler.


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

Bump `version` in `pyproject.toml` and push a tag with the same value (e.g. `0.9.0`). The `Wheels` workflow builds the wheels with cibuildwheel, the sdist and a pure Python fallback wheel, and publishes them to PyPI through trusted publishing.

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
