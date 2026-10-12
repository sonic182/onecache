"""Build the optional Cython extension; falls back to pure Python when it cannot be built.

Environment variables:
    * ONECACHE_NO_EXTENSIONS (any non-empty value): skip the extension (pure Python package).
    * ONECACHE_REQUIRE_EXTENSIONS (any non-empty value): fail the build instead of falling back.
"""

import os
import platform

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext

NO_EXTENSIONS = bool(os.environ.get("ONECACHE_NO_EXTENSIONS"))
REQUIRE_EXTENSIONS = bool(os.environ.get("ONECACHE_REQUIRE_EXTENSIONS"))


def extensions():
    if NO_EXTENSIONS or platform.python_implementation() != "CPython":
        return []
    try:
        from Cython.Build import cythonize
    except ImportError:
        if REQUIRE_EXTENSIONS:
            raise
        print("onecache: Cython not available, building pure Python package")
        return []
    return cythonize(
        [Extension("onecache._ccore", ["onecache/_ccore.pyx"])],
        compiler_directives={"language_level": 3},
    )


class OptionalBuildExt(build_ext):
    def run(self):
        try:
            super().run()
        except Exception as exc:
            self._fallback(exc)

    def build_extension(self, ext):
        try:
            super().build_extension(ext)
        except Exception as exc:
            self._fallback(exc)

    def _fallback(self, exc):
        if REQUIRE_EXTENSIONS:
            raise exc
        print(f"onecache: failed to build extension ({exc}), using pure Python")


setup(
    license="MIT",
    ext_modules=extensions(),
    cmdclass={"build_ext": OptionalBuildExt},
)
