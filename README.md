
[![Coverage Status](https://coveralls.io/repos/github/sonic182/onecache/badge.svg?branch=master)](https://coveralls.io/github/sonic182/onecache?branch=master)
![github status](https://github.com/sonic182/onecache/actions/workflows/python.yml/badge.svg)
# OneCache

Python cache for sync and async code.

Cache is not LRU, just keeps `maxsize` items in cache and drops the oldest whenever it needs to store a new item. Cache can optionally have TTL.

Tested in python 3.6 and 3.9, for windows, mac and linux (see github status badge), it should work in versions between them.

# Usage

```python
from onecache import CacheDecodator
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
    def mycoro(counter: Counter):
        counter.count += 1
        return counter.count

    assert 1 == (mycoro(counter))
    assert 1 == (mycoro(counter))
```

Decorator classes supports the following arguments

* maxsize (int): Maximun size of cache. default: 512
* ttl (int): time to expire in milliseconds, if None, it does not expire. default: None
* skip_args (bool): apply cache as the function doesn't have any arguments, default: False

If num of records exceds maxsize, it drops the oldest.


# TODO

* LRU cache

# Development

Install packages with pip-tools:
```bash
pip install pip-tools
pip-compile
pip-compile dev-requirements.in
pip-sync requirements.txt dev-requirements.txt
```

# Contribute

1. Fork
2. create a branch `feature/your_feature`
3. commit - push - pull request

Thanks :)
