
[![Coverage Status](https://coveralls.io/repos/github/sonic182/onecache/badge.svg?branch=master)](https://coveralls.io/github/sonic182/onecache?branch=master)
![github status](https://github.com/sonic182/onecache/actions/workflows/python.yml/badge.svg)
# OneCache

Python cache for sync and async code.

Cache uses LRU algoritm. Cache can optionally have TTL.

Tested in python 3.6 and 3.9, for windows, mac and linux (see github status badge), it should work in versions between them.

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
* **max_mem_size (int)**: max mem size in bytes. Ceil for sum of cache values sizes. default=None which means no limit

If num of records exceds maxsize, it drops the oldest.


# Development

Install packages with pip-tools:
```bash
pip install pip-tools
pip-compile
pip-compile test-requirements.in
pip-sync requirements.txt test-requirements.txt
```

# Contribute

1. Fork
2. create a branch `feature/your_feature`
3. commit - push - pull request

Thanks :)
