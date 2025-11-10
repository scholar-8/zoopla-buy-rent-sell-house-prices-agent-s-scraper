thonimport logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Iterable, List, Optional

import requests

from utils.parser import parse_agent_listings
from utils.proxy_manager import ProxyManager

LOGGER = logging.getLogger("zoopla_scraper.agent_extractor")

class AgentExtractor:
    """Extractor for Zoopla estate agent directory pages."""

    def __init__(
        self,
        proxy_manager: ProxyManager,
        max_items: Optional[int] = None,
        concurrency: int = 5,
        timeout: int = 30,
    ) -> None:
        self.proxy_manager = proxy_manager
        self.max_items = max_items
        self.concurrency = max(1, concurrency)
        self.timeout = timeout

    def extract(self, urls: Iterable[str]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        url_list = [u for u in urls if u]
        if not url_list:
            LOGGER.warning("No agent URLs provided; nothing to extract.")
            return results

        LOGGER.info("Extracting agents from %d URL(s)", len(url_list))

        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            future_to_url = {
                executor.submit(self._fetch_and_parse, url): url for url in url_list
            }
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    items = future.result()
                except Exception as exc:  # pragma: no cover - defensive
                    LOGGER.error("Failed to extract agents from %s: %s", url, exc)
                    continue
                results.extend(items)
                if self.max_items is not None and len(results) >= self.max_items:
                    LOGGER.info(
                        "Reached max_items limit (%d); stopping early.", self.max_items
                    )
                    return results[: self.max_items]

        return results

    def _fetch_and_parse(self, url: str) -> List[Dict[str, Any]]:
        LOGGER.debug("Fetching agent directory page: %s", url)
        proxies = self.proxy_manager.get_next_proxy()
        try:
            resp = requests.get(
                url,
                timeout=self.timeout,
                proxies=proxies,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; ZooplaScraper/1.0; +https://bitbash.dev/)"
                },
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            LOGGER.error("Request failed for %s: %s", url, exc)
            return []

        html = resp.text
        items = parse_agent_listings(html)
        LOGGER.info("Parsed %d agent(s) from %s", len(items), url)
        return items