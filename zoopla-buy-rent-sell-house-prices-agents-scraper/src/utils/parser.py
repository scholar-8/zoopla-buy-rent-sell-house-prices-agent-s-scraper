thonimport json
import logging
from typing import Any, Dict, Iterable, List

from bs4 import BeautifulSoup

LOGGER = logging.getLogger("zoopla_scraper.parser")

def _extract_json_ld(html: str) -> Iterable[Dict[str, Any]]:
    """Extract JSON-LD structures embedded in the page."""
    soup = BeautifulSoup(html, "lxml")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            yield data
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    yield item

def parse_property_listings(html: str) -> List[Dict[str, Any]]:
    """Parse property listing data from Zoopla HTML.

    This implementation prefers structured JSON-LD data but falls back to
    simple DOM-based extraction for robustness.
    """
    properties: List[Dict[str, Any]] = []

    # First, try JSON-LD
    for block in _extract_json_ld(html):
        if block.get("@type") in {"Offer", "SingleFamilyResidence", "Apartment", "House"}:
            try:
                props = _map_json_ld_to_property(block)
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.debug("Failed to map JSON-LD property block: %s", exc)
                continue
            properties.append(props)

    if properties:
        return properties

    # Fallback: DOM parsing
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("[data-listing-id]")
    for card in cards:
        listing_id = card.get("data-listing-id")
        title_el = card.select_one("h2, h3")
        price_el = card.select_one(".css-1e28vvi, .css-1e4fdj9, .price")
        address_el = card.select_one("[data-testid='listing-card-address'], .css-1f3n3r9, .address")
        link_el = card.select_one("a[href*='/for-sale/'], a[href*='/to-rent/'], a[href*='/details/']")
        property_type_el = card.select_one("[data-testid='listing-card-subtitle'], .property-type")
        agent_el = card.select_one("[data-testid='listing-card-agent-name'], .agent_name")

        if not listing_id:
            continue

        property_data: Dict[str, Any] = {
            "listingId": listing_id,
            "url": link_el["href"] if link_el and link_el.has_attr("href") else None,
            "title": title_el.get_text(strip=True) if title_el else None,
            "price": _parse_price(price_el.get_text(strip=True)) if price_el else None,
            "address": address_el.get_text(strip=True) if address_el else None,
            "property_type": property_type_el.get_text(strip=True) if property_type_el else None,
            "category": None,
            "num_bedrooms": None,
            "num_bathrooms": None,
            "num_reception_rooms": None,
            "description": None,
            "features": [],
            "agent_name": agent_el.get_text(strip=True) if agent_el else None,
            "agent_phone": None,
            "agent_logo": None,
            "coordinates": None,
            "tenure": None,
            "council_tax_band": None,
            "broadband": None,
            "transport": None,
            "images": [],
            "floorplans": [],
            "price_history": {},
            "publication_status": None,
        }
        properties.append(property_data)

    return properties

def _map_json_ld_to_property(block: Dict[str, Any]) -> Dict[str, Any]:
    offer = block
    listing_id = (
        offer.get("sku")
        or offer.get("productID")
        or offer.get("identifier", {}).get("value")
    )
    price = None
    currency = None
    if "priceSpecification" in offer:
        price_info = offer["priceSpecification"]
        price = price_info.get("price")
        currency = price_info.get("priceCurrency")
    elif "price" in offer:
        price = offer.get("price")
        currency = offer.get("priceCurrency")

    address_data = offer.get("itemOffered", {}).get("address") or {}
    coordinates = offer.get("itemOffered", {}).get("geo") or {}

    property_data: Dict[str, Any] = {
        "listingId": listing_id,
        "url": offer.get("url"),
        "title": offer.get("name"),
        "price": price,
        "currency": currency,
        "address": " ".join(
            str(address_data.get(k, ""))
            for k in ("streetAddress", "addressLocality", "postalCode")
            if address_data.get(k)
        )
        or None,
        "property_type": offer.get("itemOffered", {}).get("@type"),
        "category": offer.get("category"),
        "num_bedrooms": offer.get("itemOffered", {}).get("numberOfRooms"),
        "num_bathrooms": offer.get("itemOffered", {}).get("numberOfBathroomsTotal"),
        "num_reception_rooms": None,
        "description": offer.get("description"),
        "features": offer.get("amenityFeature", []),
        "agent_name": offer.get("seller", {}).get("name"),
        "agent_phone": offer.get("seller", {}).get("telephone"),
        "agent_logo": offer.get("seller", {}).get("image"),
        "coordinates": {
            "latitude": coordinates.get("latitude"),
            "longitude": coordinates.get("longitude"),
        }
        if coordinates
        else None,
        "tenure": offer.get("leaseLength") or offer.get("tenure"),
        "council_tax_band": None,
        "broadband": None,
        "transport": None,
        "images": offer.get("image", []),
        "floorplans": [],
        "price_history": {},
        "publication_status": offer.get("availability"),
    }
    return property_data

def _parse_price(raw: str) -> Any:
    # Extract numeric price from text like "£705,000"
    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    try:
        return int(digits) if digits else None
    except ValueError:
        LOGGER.debug("Failed to parse price from %r", raw)
        return None

def parse_agent_listings(html: str) -> List[Dict[str, Any]]:
    """Parse agent and branch information from Zoopla HTML."""
    agents: List[Dict[str, Any]] = []

    soup = BeautifulSoup(html, "lxml")

    # Try JSON-LD first
    for block in _extract_json_ld(html):
        if block.get("@type") in {"RealEstateAgent", "Organization"}:
            agent = {
                "name": block.get("name"),
                "url": block.get("url"),
                "telephone": block.get("telephone"),
                "logo": block.get("logo"),
                "address": block.get("address"),
                "aggregate_rating": block.get("aggregateRating"),
            }
            agents.append(agent)

    if agents:
        return agents

    # Fallback DOM parsing for agents directory
    cards = soup.select("[data-testid='agent-card'], .agent-card")
    for card in cards:
        name_el = card.select_one("h2, h3, .agent-name")
        phone_el = card.select_one("a[href^='tel:'], .agent-phone")
        logo_el = card.select_one("img")
        address_el = card.select_one(".agent-address, address")
        url_el = card.select_one("a[href]")

        agent: Dict[str, Any] = {
            "name": name_el.get_text(strip=True) if name_el else None,
            "telephone": (phone_el.get("href") or "").replace("tel:", "") if phone_el else None,
            "logo": logo_el.get("src") if logo_el and logo_el.has_attr("src") else None,
            "address": address_el.get_text(strip=True) if address_el else None,
            "url": url_el.get("href") if url_el and url_el.has_attr("href") else None,
        }
        agents.append(agent)

    return agents

def parse_house_prices(html: str) -> List[Dict[str, Any]]:
    """Parse sold house price information from Zoopla HTML."""
    records: List[Dict[str, Any]] = []

    soup = BeautifulSoup(html, "lxml")

    # Attempt JSON-LD extraction first
    for block in _extract_json_ld(html):
        if block.get("@type") in {"Offer", "Product"} and "price" in block:
            address = block.get("itemOffered", {}).get("address", {})
            coordinates = block.get("itemOffered", {}).get("geo", {})
            record: Dict[str, Any] = {
                "address": " ".join(
                    str(address.get(k, ""))
                    for k in ("streetAddress", "addressLocality", "postalCode")
                    if address.get(k)
                )
                or None,
                "price": block.get("price"),
                "currency": block.get("priceCurrency"),
                "date_sold": block.get("validFrom"),
                "coordinates": {
                    "latitude": coordinates.get("latitude"),
                    "longitude": coordinates.get("longitude"),
                }
                if coordinates
                else None,
            }
            records.append(record)

    if records:
        return records

    # Fallback to table-based parsing
    rows = soup.select("table tr")
    for row in rows:
        cols = [col.get_text(strip=True) for col in row.find_all("td")]
        if len(cols) < 3:
            continue
        address, price_text, date_text = cols[:3]
        record = {
            "address": address,
            "price": _parse_price(price_text),
            "currency": None,
            "date_sold": date_text,
            "coordinates": None,
        }
        records.append(record)

    return records