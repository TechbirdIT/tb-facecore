"""Main entry point for edge client application."""

import argparse
import logging

from edge_client.capture import run_capture
from edge_client.config import load_config
from edge_client.frappe_client import FrappeClient
from edge_client.store import Store

logger = logging.getLogger(__name__)
MODEL_VERSION = "buffalo_l"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Edge device client for face recognition attendance"
    )
    parser.add_argument("--config", required=True, help="Path to YAML config")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    cfg = load_config(args.config)
    from facecore import FaceAnalyzer

    analyzer = FaceAnalyzer(device="cpu", det_thresh=cfg.min_det_score)
    client = FrappeClient(cfg.frappe_url, cfg.api_key, cfg.api_secret)
    store = Store(cfg.db_path)

    logger.info("edge client starting: %s", cfg.edge_id)
    run_capture(analyzer, client, store, cfg, MODEL_VERSION)


if __name__ == "__main__":
    main()
