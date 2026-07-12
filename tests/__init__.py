"""Isolate mutable Claudio data from both the checkout and real user profile."""
import atexit
import os
import shutil
import tempfile


_TEST_HOME = tempfile.mkdtemp(prefix="claudio-tests-")
os.environ.setdefault("CLAUDIO_HOME", _TEST_HOME)
atexit.register(shutil.rmtree, _TEST_HOME, ignore_errors=True)
