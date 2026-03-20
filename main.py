import sys
import time

from app import MusicDeskApp
from server_backend import EmbeddedServer


if __name__ == "__main__":
    # `python main.py` -> desktop app with embedded local server
    # `python main.py server` -> local API server only
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "app"
    if mode == "server":
        server = EmbeddedServer()
        server.start()
        print(f"PulseDock server running on {server.base_url}")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            server.stop()
    else:
        MusicDeskApp().run()
