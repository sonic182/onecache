# AGENTS.md

This file provides guidance to AI coding agents (Claude Code, Codex, etc.) when working with code in this repository.

## Project

`onecache` is a dependency-free Python library (published to PyPI) providing in-memory caching decorators for sync and async functions, with LRU eviction, optional per-entry TTL, optional thread safety, and an optional memory-size cap. The cache core exists twice: a Cython extension (`onecache/_ccore.pyx`) used on CPython, and a pure Python fallback (`onecache/_core.py`) used on PyPy or when the extension isn't available. `requires-python` is `>=3.8`, but CI only tests 3.10 and 3.14 (and PyPy 3.11). Code must still stay compatible with Python 3.8, so don't use newer syntax such as `X | Y` unions, `match`, or builtin generics in runtime annotations.

## Commands

```bash
poetry install --with test,dev                          # install deps (Poetry 2; it does NOT build the extension)
make build_ext                                          # build the Cython extension in place; rerun after editing _ccore.pyx
poetry run pytest                                       # run all tests against the compiled backend (pytest.ini adds coverage)
ONECACHE_NO_EXTENSIONS=1 poetry run pytest              # run all tests against the pure Python backend
poetry run pytest tests/unit/test_cache.py::test_lru    # run a single test
poetry run flake8                                       # lint
python -c "import onecache; print(onecache.COMPILED)"   # check which backend is loaded
```

`tox.ini` is stale, and the Sphinx targets in the `Makefile` point to a `sourcedocs/` directory that doesn't exist. Don't use either.

## Build and release

- The build backend is setuptools + Cython (`pyproject.toml` `[build-system]`, `setup.py`). Poetry is only used for the dev/test dependency groups.
- `setup.py` makes the extension optional: if Cython or a compiler is missing, the build falls back to pure Python. `ONECACHE_NO_EXTENSIONS=1` skips the extension (it's also checked at import time in `onecache/__init__.py`), and `ONECACHE_REQUIRE_EXTENSIONS=1` turns a failed build into an error (CI and cibuildwheel set it).
- `.github/workflows/python.yml` builds in place with pip (not Poetry, so the test jobs don't depend on Poetry supporting each Python version) and runs the suite twice, once per backend.
- `.github/workflows/wheels.yml` builds only cp310 and cp314 wheels on pull requests (all versions on tags and manual runs), uses uv as build frontend (`build[uv]`) and caches cibuildwheel downloads. It uses cibuildwheel v3 (`[tool.cibuildwheel]` in `pyproject.toml`; v4 dropped cp38) for platform wheels, plus an sdist and a `py3-none-any` pure wheel that PyPy and unsupported platforms resolve to. Pushing a tag equal to the `pyproject.toml` version (e.g. `0.9.0`, no `v` prefix) publishes to PyPI via trusted publishing.
- `MANIFEST.in` must keep `onecache/*.pyx` in the sdist and exclude the generated `.c`.

## Architecture

`onecache/__init__.py` picks the backend (`CacheValue`, `ExpirableCache`, `LRUCache`) and defines `CacheDecorator` / `AsyncCacheDecorator`. **`_ccore.pyx` and `_core.py` must keep identical behavior and API.** Any change to one needs the same change in the other, and both test runs must pass.

- **Storage**: the internal `_data` dict maps string keys to `CacheValue` entries (`value`, `expire_at` as monotonic seconds with `inf` meaning never, `size`, `access`). The compiled backend keeps two intrusive doubly linked lists through the entries: insertion/recency order (`prev`/`next`) and expiry order (`eprev`/`enext`). The pure backend uses two `OrderedDict`s for the same purpose. Because those structures must stay in sync with `_data`, the public `cache` attribute is a read-only `MappingProxyType`; entries are only removed through `expire()`, `clear()`, eviction or expiry. The compiled backend's clock is a C `clock_gettime(CLOCK_MONOTONIC)`/`QueryPerformanceCounter`, not `time.monotonic`, so tests expire entries by setting `expire_at = -1.0`, never by computing timestamps.
- **Eviction**: `ExpirableCache` evicts the oldest inserted entry. `LRUCache` also moves an entry to the end on every hit (and increments `access`), so it evicts the least recently used. Both are O(1).
- **Expiry**: TTL is in **milliseconds** (`timeout`). Every lookup and set purges expired entries from the head of the expiry list (amortized O(1)) and checks the requested key's own `expire_at`. `refresh_ttl` and `refresh_key_ttl()` move the entry to the tail of the expiry list. A custom `refresh_key_ttl(key, milliseconds)` can leave the list out of order: expired entries behind a live head stay in memory until looked up or evicted, but lookups stay correct.
- **Decorators**: when `cache_class` is exactly `ExpirableCache` or `LRUCache`, `CacheDecorator` uses the backend's `_wrap()` fast path. In the compiled backend that's the C-level `CachedFunction`, whose `__get__` binds methods. Any other `cache_class`, including subclasses, uses the generic `key in cache` → `get`/`set` protocol, so overrides are honored. `expire()` goes through `self.get_key`, which builds string keys through `cls.serialize_key` when a subclass overrides it, so key overrides stay consistent. A sentinel distinguishes misses from cached `None` results. `AsyncCacheDecorator` uses `_make_key`/`_lookup`/`set`. The cache is exposed as `wrapper.cache`.
- **Keys**: `_make_key` keys calls like `functools.lru_cache`: a single `int`/`str` argument is the key itself, otherwise the `args` tuple, flattened with a `<kwargs>` marker and the sorted kwargs names and values. A top-level argument of exact type `list`/`dict`/`set` is detected up front, and any other unhashable key fails its hash; both fall back to `(<unhashable>, string)`, where the string comes from the old `str()`-based serializer (`_string_key`). The compiled `CachedFunction` skips the up-front hash check and only falls back when the lookup raises `TypeError`. `get_key` uses `_make_key` unless a class in the MRO overrides `serialize_key`; then it builds string keys through `cls.serialize_key` (resolved once per subclass and cached in the weak `_DEFAULT_KEY_CLASSES`). `skip_args=True` uses the constant key `"any"`. Keys must be identical in both backends.
- **Thread safety**: `thread_safe=True` guards every operation with a reentrant lock (`RLock` in the pure backend; in the compiled one a raw `PyThread` lock plus owner thread and depth), so finalizers or weakref callbacks that touch the cache while it holds the lock don't deadlock. The compiled lock tries a non-blocking acquire first and only blocks with the GIL released (that blocking wait can't be interrupted by Ctrl+C). Removal is idempotent, so reentrant calls are safe. `clear()` empties the dict in place (the `cache` view stays live) and drops the entries after releasing the lock. The decorator's lookup → call → set sequence is not atomic, so concurrent misses may call the function more than once.
- **`max_mem_size`**: tracks shallow `getsizeof` of the value, the key and, for tuple keys, each item of the key (`_key_size`), and is ignored on PyPy.

## Tests

All tests are in `tests/unit/test_cache.py` and use `pytest-asyncio` (`@pytest.mark.asyncio`) for the async decorator. Tests that depend on memory sizes are skipped on PyPy via `IS_PYPY`.
