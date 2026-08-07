"""Allow `python -m retrade`."""

from retrade.main import main

if __name__ == "__main__":
    raise SystemExit(main())
