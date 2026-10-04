"""Execution backends. All share the Executor interface in base.py."""

from .base import Executor, finalize_outputs
from .local import LocalExecutor

__all__ = ["Executor", "LocalExecutor", "finalize_outputs"]
