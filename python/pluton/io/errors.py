"""Exception hierarchy for .pluton load/save.

A PlutonIOError means 'this file is bad' (we own the message). OS-level errors
(permission, disk full) are left to propagate as OSError so the UI can tell the
two apart.
"""

from __future__ import annotations


class PlutonIOError(Exception):
    """Base for all .pluton load/save errors that mean 'this file is bad'."""


class PlutonFormatError(PlutonIOError):
    """Not a valid .pluton document: bad zip, missing entries, malformed structure."""


class PlutonVersionError(PlutonIOError):
    """The file's schema_version is newer than this build supports."""
