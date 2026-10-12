"""Compare onecache with functools.lru_cache and print a markdown table.

Usage: python benchmarks/compare_lru_cache.py
"""

import functools
import itertools
import json
import os
import platform
import subprocess
import sys
import timeit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CASES = [
    ("hit_1_arg", "Hit, 1 positional arg"),
    ("hit_kwargs", "Hit, 2 args + 1 kwarg"),
    ("miss_full", "Miss on a full cache (evicts)"),
    ("hit_thread_safe", "Hit, thread safe¹"),
    ("hit_ttl", "Hit, with ttl"),
    ("hit_list", "Hit, list argument"),
]
MAXSIZE = 512


def target(a, b=None, c=None):
    return a


def lru_cache_cases():
    cached = functools.lru_cache(maxsize=MAXSIZE)(target)
    counter = itertools.count()
    cached(1)
    cached(1, "x", c=3)
    for _ in range(MAXSIZE * 2):
        cached(next(counter))
    return {
        "hit_1_arg": lambda: cached(1),
        "hit_kwargs": lambda: cached(1, "x", c=3),
        "miss_full": lambda: cached(next(counter)),
        "hit_thread_safe": lambda: cached(1),
        "hit_ttl": None,
        "hit_list": None,
    }


def onecache_cases():
    from onecache import CacheDecorator

    plain = CacheDecorator(maxsize=MAXSIZE)(target)
    safe = CacheDecorator(maxsize=MAXSIZE, thread_safe=True)(target)
    ttl = CacheDecorator(maxsize=MAXSIZE, ttl=60000)(target)
    counter = itertools.count()
    for cached in (plain, safe, ttl):
        cached(1)
    plain(1, "x", c=3)
    plain([1, 2])
    for _ in range(MAXSIZE * 2):
        plain(next(counter))
    return {
        "hit_1_arg": lambda: plain(1),
        "hit_kwargs": lambda: plain(1, "x", c=3),
        "miss_full": lambda: plain(next(counter)),
        "hit_thread_safe": lambda: safe(1),
        "hit_ttl": lambda: ttl(1),
        "hit_list": lambda: plain([1, 2]),
    }


def measure(cases):
    results = {}
    for name, func in cases.items():
        if func is None:
            results[name] = None
            continue
        timer = timeit.Timer(func)
        number, _ = timer.autorange()
        best = min(timer.repeat(repeat=7, number=number))
        results[name] = best / number * 1e9
    return results


def measure_onecache(pure):
    env = dict(os.environ)
    env.pop("ONECACHE_NO_EXTENSIONS", None)
    if pure:
        env["ONECACHE_NO_EXTENSIONS"] = "1"
    output = subprocess.check_output([sys.executable, __file__, "--onecache-json"], env=env)
    return json.loads(output)


def cell(value):
    return "n/a" if value is None else f"{value:,.0f}"


def ratio(value, baseline):
    if value is None or baseline is None:
        return "n/a"
    factor = value / baseline
    if factor >= 1:
        return f"{factor:.1f}x slower"
    return f"{1 / factor:.1f}x faster"


def main():
    if sys.argv[1:] == ["--onecache-json"]:
        import onecache

        print(json.dumps({"compiled": onecache.COMPILED, "results": measure(onecache_cases())}))
        return

    compiled = measure_onecache(pure=False)
    if not compiled["compiled"]:
        sys.exit("onecache extension is not built, run `make build_ext` first")
    baseline = measure(lru_cache_cases())
    pure = measure_onecache(pure=True)

    print(f"Python {platform.python_version()} ({platform.python_implementation()}), "
          f"{platform.system()} {platform.machine()}, maxsize={MAXSIZE}, ns per call (lower is better)\n")
    print("| Case | lru_cache | onecache (Cython) | Cython vs lru_cache | onecache (pure Python) |")
    print("|---|---|---|---|---|")
    for name, label in CASES:
        print(
            f"| {label} | {cell(baseline[name])} | {cell(compiled['results'][name])} "
            f"| {ratio(compiled['results'][name], baseline[name])} | {cell(pure['results'][name])} |"
        )


if __name__ == "__main__":
    main()
