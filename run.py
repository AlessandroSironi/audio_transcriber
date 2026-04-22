#!/usr/bin/env python3
"""
Audio Transcriber — entrypoint.

Usage:
  python run.py               # normal start; opens browser automatically
  python run.py --no-browser  # headless / SSH mode
  python run.py --setup       # force re-run CLI setup wizard
  python run.py --port 9000   # custom port
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Ensure the project root is on sys.path when run directly
sys.path.insert(0, str(Path(__file__).parent))


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Audio Transcriber")
    p.add_argument("--no-browser", action="store_true", help="Do not open browser on start")
    p.add_argument("--setup",      action="store_true", help="Re-run CLI setup wizard")
    p.add_argument("--port",       type=int, default=None, help="Override port (default from config or 8000)")
    p.add_argument("--host",       type=str, default=None, help="Override bind host (default 0.0.0.0)")
    return p.parse_args()


# ---------------------------------------------------------------------------
# CLI setup wizard (fallback / --setup mode)
# ---------------------------------------------------------------------------

def run_cli_wizard() -> None:
    """Interactive terminal wizard for headless / SSH use."""
    from app.config import save_settings
    from app.core.audio import check_ffmpeg

    print("\n╔══════════════════════════════════════╗")
    print("║   Audio Transcriber — Setup Wizard   ║")
    print("╚══════════════════════════════════════╝\n")

    # ffmpeg check
    if not check_ffmpeg():
        print("⚠  ffmpeg not found in PATH.")
        if sys.platform == "darwin":
            print("   Install with:  brew install ffmpeg")
        else:
            print("   Install with:  sudo apt install ffmpeg")
        print()

    # Storage dir
    default_storage = str(Path.home() / "AudioTranscriptions")
    storage_dir = input(f"Storage directory [{default_storage}]: ").strip() or default_storage

    # Model size
    print("\nModel size:")
    sizes = ["tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"]
    for i, s in enumerate(sizes, 1):
        print(f"  [{i}] {s}")
    choice = input("Choice [6]: ").strip()
    try:
        model_size = sizes[int(choice) - 1]
    except (ValueError, IndexError):
        model_size = "large-v3"

    # Save config
    save_settings({
        "storage_dir": storage_dir,
        "whisper_model": model_size,
    })
    print("\n✓ Configuration saved.")

    # Download models
    print("\nDownloading models (this may take a while) …\n")
    from setup.download_models import download_all
    download_all(model_size=model_size)
    print("\n✓ Setup complete. Run  python run.py  to start the server.\n")


# ---------------------------------------------------------------------------
# LAN IP detection
# ---------------------------------------------------------------------------

def get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ---------------------------------------------------------------------------
# Browser auto-open
# ---------------------------------------------------------------------------

def open_browser(url: str, delay: float = 1.2) -> None:
    def _open() -> None:
        time.sleep(delay)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    if args.setup:
        run_cli_wizard()
        return

    # Load config (may or may not exist)
    from app.config import is_configured, load_settings
    configured = is_configured()
    settings = load_settings()

    host = args.host or settings.host or "0.0.0.0"
    port = args.port or settings.port or 8000
    lan_ip = get_lan_ip()

    print("\n  🎙  Audio Transcriber")
    print(f"  Local:    http://localhost:{port}")
    if host == "0.0.0.0":
        print(f"  Network:  http://{lan_ip}:{port}")
    print()

    if not configured:
        print("  First run detected — opening setup wizard in browser.\n")

    # Schedule browser open
    if not args.no_browser:
        target_path = "/" if configured else "/setup"
        open_browser(f"http://localhost:{port}{target_path}")

    # Start uvicorn
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
