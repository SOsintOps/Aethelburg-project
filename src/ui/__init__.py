"""UI components — FastAPI Web & Desktop Intelligence Interface."""
from src.ui.desktop import launch_desktop
from src.ui.web_app import create_app

__all__ = ["create_app", "launch_desktop"]
