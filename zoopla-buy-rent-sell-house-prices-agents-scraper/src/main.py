thonimport argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import jsonschema

from utils.proxy_manager import ProxyManager
from extractors.property_extractor import PropertyExtractor
from extractors.agent_extractor import AgentExtractor
from extractors.house_prices_extractor import HousePricesExtractor

LOGGER = logging.getLogger("zoopla_scraper")

def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

def load_schema() -> Dict[str, Any]:
    current_dir = Path(__file__).resolve().parent
    schema_path = current_dir / "config" / "input_schema.json"
    with schema_path.open("r", encoding="utf-8") as f:
        return json.load(f)

def default_config() -> Dict[str, Any]:
    project_root = Path(__file__).resolve().parents[1]
    data_dir = project_root / "data"
    return {
        "mode": "all",
        "property_urls": [
            "https://www.zoopla.co.uk/for-sale/property/london/",
        ],
        "agent_urls": [
            "https://www.zoopla.co.uk/find-agents/london/",
        ],
        "house_price_urls": [
            "https://www.zoopla.co.uk/house-prices/london/",
        ],
        "output_format": "json",
        "output_dir": str(data_dir),
        "max_items": 100,
        "concurrency": 5,
        "use_proxies": False,
        "proxies": [],
    }

def load_config(config_path: Optional[str]) -> Dict[str, Any]:
    schema = load_schema()
    if config_path:
        config_file = Path(config_path)
        if not config_file.is_file():
            raise FileNotFoundError(f"Config file not found: {config_file}")
        with config_file.open("r", encoding="utf-8") as f:
            config = json.load(f)
    else:
        config = default_config()

    try:
        jsonschema.validate(instance=config, schema=schema)
    except jsonschema.ValidationError as exc:
        raise ValueError(f"Config validation error: {exc.message}") from exc
    return config

def ensure_output_dir(directory: str) -> Path:
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    return path

def write_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    LOGGER.info("Wrote JSON output to %s", path)

def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        LOGGER.warning("No rows to write to CSV at %s", path)
        return
    import csv

    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    LOGGER.info("Wrote CSV output to %s", path)

def run(config: Dict[str, Any]) -> None:
    output_dir = ensure_output_dir(config["output_dir"])
    proxy_manager = ProxyManager(
        proxies=config.get("proxies") or [],
        enabled=config.get("use_proxies", False),
    )

    mode = config["mode"]
    output_format = config["output_format"].lower()
    max_items = int(config.get("max_items") or 0) or None
    concurrency = int(config.get("concurrency") or 1)

    property_extractor = PropertyExtractor(
        proxy_manager=proxy_manager,
        max_items=max_items,
        concurrency=concurrency,
    )
    agent_extractor = AgentExtractor(
        proxy_manager=proxy_manager,
        max_items=max_items,
        concurrency=concurrency,
    )
    house_prices_extractor = HousePricesExtractor(
        proxy_manager=proxy_manager,
        max_items=max_items,
        concurrency=concurrency,
    )

    if mode not in {"property", "agent", "house_prices", "all"}:
        raise ValueError(f"Unsupported mode: {mode}")

    if mode in {"property", "all"}:
        property_urls = config.get("property_urls") or []
        LOGGER.info("Starting property extraction for %d URL(s)", len(property_urls))
        property_rows = property_extractor.extract(property_urls)
        if output_format == "json":
            write_json(output_dir / "sample_property.json", property_rows)
        elif output_format == "csv":
            write_csv(output_dir / "properties.csv", property_rows)
        else:
            raise ValueError(f"Unsupported output format: {output_format}")

    if mode in {"agent", "all"}:
        agent_urls = config.get("agent_urls") or []
        LOGGER.info("Starting agent extraction for %d URL(s)", len(agent_urls))
        agent_rows = agent_extractor.extract(agent_urls)
        if output_format == "json":
            write_json(output_dir / "agents.json", agent_rows)
        elif output_format == "csv":
            write_csv(output_dir / "agents.csv", agent_rows)
        else:
            raise ValueError(f"Unsupported output format: {output_format}")

    if mode in {"house_prices", "all"}:
        hp_urls = config.get("house_price_urls") or []
        LOGGER.info("Starting house price extraction for %d URL(s)", len(hp_urls))
        hp_rows = house_prices_extractor.extract(hp_urls)
        if output_format == "json":
            write_json(output_dir / "house_prices.json", hp_rows)
        elif output_format == "csv":
            write_csv(output_dir / "house_prices.csv", hp_rows)
        else:
            raise ValueError(f"Unsupported output format: {output_format}")

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Zoopla | Buy | Rent | Sell | House Prices | Agent(s) | Scraper"
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to JSON configuration file matching src/config/input_schema.json",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["property", "agent", "house_prices", "all"],
        help="Override scraping mode defined in config file",
    )
    parser.add_argument(
        "--output-format",
        type=str,
        choices=["json", "csv"],
        help="Override output format defined in config file",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )
    return parser.parse_args(argv)

def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    setup_logging(verbose=args.verbose)

    try:
        config = load_config(args.config)
    except Exception as exc:
        LOGGER.error("Failed to load configuration: %s", exc)
        raise SystemExit(1)

    if args.mode:
        config["mode"] = args.mode
    if args.output_format:
        config["output_format"] = args.output_format

    try:
        run(config)
    except Exception as exc:
        LOGGER.exception("Scraper run failed: %s", exc)
        raise SystemExit(1)

if __name__ == "__main__":
    main()