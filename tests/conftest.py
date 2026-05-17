"""Shared pytest fixtures and configuration."""

import os

import pytest


# Ensure Qt uses the offscreen platform in CI / headless environments.
# This must run BEFORE QApplication is created (i.e., before any pytest-qt fixture).
if os.environ.get("CI") == "true" or os.environ.get("QT_QPA_PLATFORM"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
