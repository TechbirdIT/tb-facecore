"""Main entry point for edge client application."""

import argparse
import logging


logger = logging.getLogger(__name__)


def main():
    """Run the edge client."""
    parser = argparse.ArgumentParser(
        description="Edge device client for face recognition attendance"
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to YAML config file (see config.example.yaml)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    logger.info(f"Starting edge client with config: {args.config}")
    # Stub — will be implemented in phase 4
    raise NotImplementedError("Edge client main loop — phase 4 implementation")


if __name__ == "__main__":
    main()
