"""Exception hierarchy. Every error the CLI reports cleanly derives from ResearchError."""

from __future__ import annotations


class ResearchError(Exception):
    """Base class for all expected, user-facing errors."""


class ProjectNotFound(ResearchError):
    """No project.yaml was found in the directory or any of its parents."""


class ConfigError(ResearchError):
    """A configuration file is missing, malformed or fails schema validation."""


class ApprovalRequired(ResearchError):
    """An operation needs an explicit researcher approval that has not been given."""


class DatasetNotValidated(ResearchError):
    """An experiment references a dataset without a passing validation report."""


class ExecutionError(ResearchError):
    """An executor could not start, monitor or collect a run."""


class EvidenceError(ResearchError):
    """A claim cannot be resolved against its declared evidence."""


class SecretDetected(ResearchError):
    """A file about to be packaged, uploaded or committed appears to contain a secret."""
