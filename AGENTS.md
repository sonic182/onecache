# AGENTS.md

This file provides guidance to AI coding agents (Claude Code, Codex, etc.) when working with code in this repository.

## Project

`onecache` is a dependency-free Python library (published to PyPI) providing in-memory caching decorators for sync and async functions, with LRU-style eviction, optional per-entry TTL, optional thread safety, and an optional memory-size cap. Supported runtimes: CPython 3.8–3.14 and PyPy 3.9 on Linux, macOS and Windows (the CI matrix in `.github/workflows/python.yml`). Code must stay compatible with Python 3.8, so don't use newer syntax such as `X | Y` unions, `match`, or builtin generics in runtime annotations.

## Commands

```bash
poetry install --with test,dev                          # install deps
poetry run pytest                                       # run all tests (pytest.ini adds coverage: term + htmlcov/)
poetry run pytest tests/unit/test_cache.py::test_cache_counter   # run a single test
poetry run flake8                                       # lint (flake8-docstrings is installed)
poetry run autopep8 --in-place --recursive onecache tests
make test310                                            # run the tests in a python:3.10 Docker container (test38…test312, or `make test` for all)
make build                                              # clean + poetry build
```

CI runs `poetry run pytest --maxfail=1 --disable-warnings -q`. `tox.ini` is stale (py27/`setup.py`), and the Sphinx targets in the `Makefile` point to a `sourcedocs/` directory that doesn't exist. Don't use either.

## Architecture

All public API lives in `onecache/__init__.py`. `CacheValue` (`onecache/cache_value.py`) wraps each stored value with its access count, expiry timestamp and `getsizeof` size. `onecache/utils.py` provides `IS_PYPY` and a version-aware `utcnow()`.

- **`ExpirableCache`**: an `OrderedDict` of string keys mapped to `CacheValue`. Eviction pops the oldest inserted key. TTL is in **milliseconds**. Every `get` and `__contains__` call goes through `_check_expired`, which scans and removes *all* expired entries (O(n)), not just the requested key. `max_mem_size` tracks `getsizeof(key) + getsizeof(value)` (shallow sizes) and is forced to `None` on PyPy; `CacheValue.size` is also `None` there.
- **`LRUCache(ExpirableCache)`** (the default `cache_class`): despite its name, `_pop_one` evicts the entry with the **lowest access count** (LFU-like, by sorting the whole cache), and `get` increments that count.
- **`CacheDecorator` / `AsyncCacheDecorator`**: they build a cache instance from the constructor args (`maxsize`, `ttl`, `refresh_ttl`, `thread_safe`, `max_mem_size` are passed positionally/by keyword into `cache_class(size, timeout, ...)`, so a custom `cache_class` must accept that signature). The wrapper checks `key in cache`, then either calls the function and `set`s the result or returns `cache.get(key)`. The cache instance is exposed as `wrapper.cache`, which is how callers and tests inspect it or call `.expire(*args, **kwargs)`.
- **Keys**: `get_key` joins `serialize_key` of each positional arg plus the sorted `k=v` kwargs with `-`. Dicts and lists are serialized recursively, and everything else goes through `str()`. Objects without a custom `__str__` therefore key by their default repr (identity), and distinct args can collide (e.g. `"a-b"` vs `("a", "b")`). `skip_args=True` uses the constant key `"any"`.
- **Thread safety**: when `thread_safe=True`, a single `Lock` guarded by `_scoped()` covers `set`, TTL refresh and access increments. Expiry scans and the decorator's contains-then-get sequence are not locked.

## Tests

All tests are in `tests/unit/test_cache.py` and use `pytest-asyncio` (`@pytest.mark.asyncio`) for the async decorator. Tests that depend on memory sizes are skipped or adjusted on PyPy via `IS_PYPY`.
