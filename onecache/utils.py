import datetime
import platform
import sys

IS_PYPY = platform.python_implementation().lower().startswith("pypy")

def utcnow():
    if sys.version_info >= (3, 11):
        return datetime.datetime.now(datetime.UTC)
    else:
        return datetime.datetime.utcnow()
