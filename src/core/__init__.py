"""Core modules: service registry, logging, shared utilities."""
from src.core.service_registry import ServiceRegistry
from src.core.logging import setup_logging

__all__ = ["ServiceRegistry", "setup_logging"]
