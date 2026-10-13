"""Aethelburg — Application entry point."""


def main() -> None:
    """Start the Aethelburg application."""
    from src.core.logging import setup_logging

    setup_logging()
    print("Aethelburg v0.1.0 — Shell Company Detection Platform")
    print("Use --help for available commands")
    # UI initialization will be added in Phase 2b


if __name__ == "__main__":
    main()
