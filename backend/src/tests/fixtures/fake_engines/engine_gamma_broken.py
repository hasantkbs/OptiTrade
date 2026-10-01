"""Fixture: a fake engine module that fails at import time, used to prove
discover_engines() logs and skips a broken module rather than aborting
discovery of the rest of the package."""
raise RuntimeError("simulated broken engine module")
