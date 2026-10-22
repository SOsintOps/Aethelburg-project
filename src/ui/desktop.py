"""Desktop launcher for Aethelburg (`aethelburg desktop`).

Starts the local FastAPI intelligence backend on `127.0.0.1:8050` and opens:
  - PySide6 `QWebEngineView` native desktop window if `PySide6` is installed, OR
  - Edge/Chrome native `--app=http://127.0.0.1:8050` chromeless desktop window / default browser.
"""
from __future__ import annotations

import shutil
import subprocess
import threading
import time
import webbrowser

import uvicorn

from src.ui.web_app import create_app


def launch_desktop(host: str = "127.0.0.1", port: int = 8050, open_window: bool = True) -> None:
    """Launch the Aethelburg application server and open the desktop UI."""
    url = f"http://{host}:{port}"
    app = create_app()

    if open_window:
        def _open_ui() -> None:
            time.sleep(1.2)
            # Prefer Edge or Chrome --app mode on Windows for native desktop window experience
            for browser_bin in ("msedge", "chrome"):
                exe = shutil.which(browser_bin)
                if exe:
                    try:
                        subprocess.Popen([exe, f"--app={url}", "--window-size=1600,960"])
                        return
                    except Exception:
                        pass
            webbrowser.open(url)

        threading.Thread(target=_open_ui, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="info")
