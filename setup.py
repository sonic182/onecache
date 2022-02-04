"""Setup module."""
import os
import sys
from shutil import which

from pkg_resources import parse_requirements
from setuptools import Extension, setup

try:
    from Cython.Build import cythonize
except ImportError:
    cythonize = None


NO_EXTENSIONS: bool = bool(os.environ.get("ONECACHE_NO_EXTENSIONS"))


if sys.implementation.name != "cpython":
    NO_EXTENSIONS = True


def no_extensions():
    is_compiler = False
    for compiler in ["gcc", "clang"]:
        is_compiler = which(compiler) is not None
    return NO_EXTENSIONS or not is_compiler 


# https://cython.readthedocs.io/en/latest/src/userguide/source_files_and_compilation.html#distributing-cython-modules
def no_cythonize(extensions, **_ignore):
    for extension in extensions:
        sources = []
        for sfile in extension.sources:
            path, ext = os.path.splitext(sfile)
            if ext in (".pyx", ".py"):
                if extension.language == "c++":
                    ext = ".cpp"
                else:
                    ext = ".c"
                sfile = path + ext
            sources.append(sfile)
        extension.sources[:] = sources
    return extensions


extensions = [
    Extension("onecache.cache_value", ["onecache/cache_value.pyx"]),
]

CYTHONIZE = bool(int(os.getenv("CYTHONIZE", 0))) and cythonize is not None

if CYTHONIZE:
    compiler_directives = {"language_level": 3, "embedsignature": True}
    extensions = cythonize(extensions, compiler_directives=compiler_directives)
else:
    extensions = no_cythonize(extensions)


def read_file(filename):
    """Read file correctly."""
    with open(filename) as _file:
        return _file.read().strip()


def requirements(filename):
    """Parse requirements from file."""
    return [str(req) for req in parse_requirements(read_file(filename))]


setup(
    name="onecache",
    version="0.4.1",
    description="Python cache for sync and async code",
    long_description=read_file("README.md"),
    long_description_content_type="text/markdown",
    author="Johanderson Mogollon",
    author_email="johander1822@gmail.com",
    license="MIT",
    packages=["onecache"],
    ext_modules=[] if no_extensions() else extensions,
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Operating System :: OS Independent",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: Implementation :: PyPy",
    ],
    install_requires=requirements("./requirements.txt"),
    extras_require={"test": requirements("./test-requirements.txt")},
)
