# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]


## [0.6.0] 2023-08-11
### Added
- Compatibility and tests for python versions 3.10 and 3.11

### Removed
- Removed all cython stuff

## [0.5.0] 2023-03-27
### Fixed
- Pypy onecache works

## [0.4.1] 2022-02-04
### Fixed
- Counting values size at decreasing

## [0.4.0] 2022-01-30
### Added
- C extension for cache value with cython

## [0.3.2] 2022-01-26
### Added
- Flag for thread safety

## [0.3.1] 2021-07-20
### Changed
- Better pop when doing set, and reaching max size

## [0.3.0] 2021-07-19
### Changed
- access map removed in favor of using cache map + CacheValue access attribute

## [0.2.0] 2021-07-19
### Added
- CacheValue class as data container
- refresh_ttl argument, for refresh ttl per key access

## [0.1.0] 2021-07-18
### Fixed
- Better serialize keys with sort

## [0.0.4] 2021-07-16
### Fixed
- TTL and LRU usage combination works as expected

## [0.0.3] 2021-07-16
### Added
- LRUCache, using it by default for decorators

## [0.0.2] 2021-07-16
### Fix
- Readme for pypi

## [0.0.1] 2021-07-16
### Added
- Cache class
- Sync and Async decorators

[Unreleased]: https://github.com/sonic182/onecache/compare/0.6.0..HEAD
[0.6.0]: https://github.com/sonic182/onecache/compare/0.5.1..0.6.0
[0.5.1]: https://github.com/sonic182/onecache/compare/0.5.0..0.5.1
[0.5.0]: https://github.com/sonic182/onecache/compare/0.4.1..0.5.0
[0.4.1]: https://github.com/sonic182/onecache/compare/0.4.0..0.4.1
[0.4.0]: https://github.com/sonic182/onecache/compare/0.3.2..0.4.0
[0.3.2]: https://github.com/sonic182/onecache/compare/0.3.1..0.3.2
[0.3.1]: https://github.com/sonic182/onecache/compare/0.3.0..0.3.1
[0.3.0]: https://github.com/sonic182/onecache/compare/0.2.0..0.3.0
[0.2.0]: https://github.com/sonic182/onecache/compare/0.1.0..0.2.0
[0.1.0]: https://github.com/sonic182/onecache/compare/0.0.4..0.1.0
[0.0.4]: https://github.com/sonic182/onecache/compare/0.0.3..0.0.4
[0.0.3]: https://github.com/sonic182/onecache/compare/0.0.2..0.0.3
[0.0.2]: https://github.com/sonic182/onecache/compare/0.0.1..0.0.2
[0.0.1]: https://github.com/sonic182/onecache/compare/814065637987644cc56a09028df955e001a2163b..0.0.1
