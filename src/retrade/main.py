"""Application entry point."""

from __future__ import annotations


def main() -> int:
    """Start Retrade. Prototype UI will be wired here later."""
    print(f"Retrade {__import__('retrade').__version__} - project initialized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
