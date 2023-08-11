"""Setup module."""

from pkg_resources import parse_requirements
from setuptools import setup



def read_file(filename):
    """Read file correctly."""
    with open(filename) as _file:
        return _file.read().strip()


def requirements(filename):
    """Parse requirements from file."""
    return [str(req) for req in parse_requirements(read_file(filename))]


setup(
    name="onecache",
    version="0.6.0",
    description="Python cache for sync and async code",
    long_description=read_file("README.md"),
    long_description_content_type="text/markdown",
    author="Johanderson Mogollon",
    author_email="johander1822@gmail.com",
    license="MIT",
    packages=["onecache"],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Operating System :: OS Independent",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: Implementation :: PyPy",
    ],
    install_requires=requirements("./requirements.txt"),
    extras_require={"test": requirements("./test-requirements.txt")},
)
