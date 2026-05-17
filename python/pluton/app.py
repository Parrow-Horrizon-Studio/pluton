"""Pluton application entry point."""

import sys


def main() -> int:
    """Application entry point. Returns process exit code."""
    from pluton import __version__
    print(f"Pluton {__version__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
