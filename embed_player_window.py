from __future__ import annotations

import sys
import webbrowser


def main() -> None:
    target_url = sys.argv[1] if len(sys.argv) > 1 else "about:blank"

    try:
        import webview  # type: ignore
    except Exception:
        webbrowser.open(target_url)
        return

    window = webview.create_window(
        "PulseDock Embedded Player",
        target_url,
        width=1220,
        height=860,
        text_select=True,
    )
    webview.start(gui="edgechromium" if sys.platform.startswith("win") else None, debug=False)


if __name__ == "__main__":
    main()
