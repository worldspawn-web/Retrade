"""Top-N USDT symbol universe with disk cache."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_LEVERAGED_SUFFIXES = ("UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT")
_STABLE_BASES = frozenset(
    {
        "USDC",
        "USD1",
        "FDUSD",
        "TUSD",
        "BUSD",
        "DAI",
        "USDP",
        "EUR",
        "AEUR",
    }
)


class SymbolUniverse:
    """Binance spot USDT pairs ranked by 24h quote volume."""

    def __init__(
        self,
        *,
        base_url: str,
        cache_path: Path,
        top_n: int = 200,
        min_quote_volume_usd: float = 5_000_000.0,
        ttl_s: int = 86_400,
        timeout_s: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._cache_path = cache_path
        self._top_n = top_n
        self._min_quote_volume_usd = min_quote_volume_usd
        self._ttl_s = ttl_s
        self._timeout = timeout_s
        self._symbols: list[str] = []

    @property
    def symbols(self) -> list[str]:
        return list(self._symbols)

    def ensure_loaded(self) -> list[str]:
        if self._symbols and not self._cache_expired():
            return self.symbols
        if self._load_cache():
            return self.symbols
        self.refresh()
        return self.symbols

    def refresh(self) -> list[str]:
        try:
            symbols = self._fetch_top()
        except (httpx.HTTPError, OSError, ValueError) as exc:
            logger.warning("Failed to refresh symbol universe: %s", exc)
            if self._load_cache(ignore_ttl=True) and self._symbols:
                return self.symbols
            self._symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
            return self.symbols

        self._symbols = symbols
        self._save_cache()
        return self.symbols

    def _fetch_top(self) -> list[str]:
        url = f"{self._base_url}/api/v3/ticker/24hr"
        with httpx.Client(timeout=self._timeout) as client:
            response = client.get(url)
            response.raise_for_status()
            payload = response.json()

        ranked: list[tuple[str, float]] = []
        for row in payload:
            symbol = str(row.get("symbol", ""))
            if not _is_tradable_usdt(symbol):
                continue
            try:
                quote_volume = float(row.get("quoteVolume", 0.0))
            except (TypeError, ValueError):
                continue
            if quote_volume < self._min_quote_volume_usd:
                continue
            ranked.append((symbol, quote_volume))

        ranked.sort(key=lambda item: item[1], reverse=True)
        return [symbol for symbol, _ in ranked[: self._top_n]]

    def _cache_meta_matches(self, raw: dict[str, object]) -> bool:
        try:
            top_n = int(raw.get("top_n", -1))  # type: ignore[arg-type]
            min_vol = float(raw.get("min_quote_volume_usd", -1))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        return (
            top_n == self._top_n
            and abs(min_vol - self._min_quote_volume_usd) < 1.0
        )

    def _cache_expired(self) -> bool:
        if not self._cache_path.exists():
            return True
        try:
            raw = json.loads(self._cache_path.read_text(encoding="utf-8"))
            if not self._cache_meta_matches(raw):
                return True
            fetched_at = float(raw.get("fetched_at", 0))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return True
        return (time.time() - fetched_at) > self._ttl_s

    def _load_cache(self, *, ignore_ttl: bool = False) -> bool:
        if not self._cache_path.exists():
            return False
        try:
            raw = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return False
        if not ignore_ttl and self._cache_expired():
            return False
        if not ignore_ttl and not self._cache_meta_matches(raw):
            return False
        try:
            symbols = [str(s).upper() for s in raw.get("symbols", [])]
        except (TypeError, ValueError):
            return False
        if not symbols:
            return False
        self._symbols = symbols[: self._top_n]
        return True

    def _save_cache(self) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "fetched_at": time.time(),
            "top_n": self._top_n,
            "min_quote_volume_usd": self._min_quote_volume_usd,
            "symbols": self._symbols,
        }
        self._cache_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _is_tradable_usdt(symbol: str) -> bool:
    if not symbol.endswith("USDT"):
        return False
    if any(symbol.endswith(suf) for suf in _LEVERAGED_SUFFIXES):
        return False
    base = symbol[: -len("USDT")]
    if base in _STABLE_BASES:
        return False
    return base.isalnum()
