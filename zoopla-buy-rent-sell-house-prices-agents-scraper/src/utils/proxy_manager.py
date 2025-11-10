thonimport itertools
import logging
from typing import Dict, Iterable, List, Optional

LOGGER = logging.getLogger("zoopla_scraper.proxy")

class ProxyManager:
    """Simple round-robin proxy manager for requests."""

    def __init__(self, proxies: Optional[Iterable[str]] = None, enabled: bool = False) -> None:
        self._enabled = enabled
        self._proxies: List[str] = list(proxies or [])
        self._cycle = itertools.cycle(self._proxies) if self._proxies else None
        if self._enabled and not self._proxies:
            LOGGER.warning("ProxyManager enabled but no proxies were provided.")

    def get_next_proxy(self) -> Optional[Dict[str, str]]:
        """Return the next proxy mapping for requests, or None if disabled."""
        if not self._enabled or not self._cycle:
            return None
        proxy_url = next(self._cycle)
        LOGGER.debug("Using proxy %s", proxy_url)
        return {
            "http": proxy_url,
            "https": proxy_url,
        }

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        if not self._proxies:
            LOGGER.warning("Cannot enable ProxyManager: no proxies available.")
            return
        self._enabled = True
        if not self._cycle:
            self._cycle = itertools.cycle(self._proxies)

    def disable(self) -> None:
        self._enabled = False