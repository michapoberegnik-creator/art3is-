from __future__ import annotations

import base64
import binascii
import json
import mimetypes
import re
import shutil
import threading
from copy import deepcopy
from pathlib import Path
from urllib.parse import quote_plus, urlparse
from urllib.request import urlopen
import html

from flask import Flask, abort, jsonify, send_file, send_from_directory
from werkzeug.serving import make_server
from werkzeug.utils import secure_filename


APP_DIR = Path(__file__).resolve().parent
DATA_FILE = APP_DIR / "data.json"
USER_MEDIA_DIR = APP_DIR / "user_media"
TRACKS_DIR = USER_MEDIA_DIR / "tracks"
BACKGROUNDS_DIR = USER_MEDIA_DIR / "backgrounds"

for directory in (USER_MEDIA_DIR, TRACKS_DIR, BACKGROUNDS_DIR):
    directory.mkdir(parents=True, exist_ok=True)


PROVIDERS = [
    {
        "id": "spotify",
        "name": "Spotify",
        "url": "https://open.spotify.com/search/{query}",
        "text_hint": "Open official Spotify results for the current query.",
    },
    {
        "id": "youtube_music",
        "name": "YouTube Music",
        "url": "https://music.youtube.com/search?q={query}",
        "text_hint": "Open official YouTube Music results for the current query.",
    },
    {
        "id": "soundcloud",
        "name": "SoundCloud",
        "url": "https://soundcloud.com/search?q={query}",
        "text_hint": "Open official SoundCloud results for the current query.",
    },
    {
        "id": "tunemymusic",
        "name": "TuneMyMusic",
        "url": "https://www.tunemymusic.com/",
        "text_hint": "Open TuneMyMusic to transfer, sync, or import the current music query across services.",
    },
]

LYRICS_SOURCES = [
    {"name": "Genius", "url": "https://genius.com/search?q={query}"},
    {"name": "YouTube", "url": "https://www.youtube.com/results?search_query={query}+lyrics"},
]

EQ_PRESETS = {
    "Flat": {"low": 0, "mid": 0, "high": 0},
    "Classic": {"low": 1, "mid": 2, "high": 3},
    "Bass Boost": {"low": 7, "mid": 1, "high": -1},
    "Vocal": {"low": -2, "mid": 5, "high": 2},
    "Treble Lift": {"low": -1, "mid": 1, "high": 6},
    "Night Mode": {"low": 2, "mid": 0, "high": -4},
    "Rock": {"low": 5, "mid": 1, "high": 4},
    "Club": {"low": 6, "mid": -1, "high": 3},
    "Studio": {"low": 1, "mid": 3, "high": 1},
    "Custom": {"low": 0, "mid": 0, "high": 0},
}

SPEED_PRESETS = {
    "Normal": 1.0,
    "Slowed": 0.88,
    "Sped Up": 1.12,
}

TOKEN_FIELDS = [
    ("spotify_client_id", "Spotify Client ID"),
    ("spotify_client_secret", "Spotify Client Secret"),
    ("spotify_redirect_uri", "Spotify Redirect URI"),
    ("spotify_ip_hint", "Spotify IP / Market Hint"),
    ("google_client_id", "Google Client ID"),
    ("google_api_key", "Google API Key"),
]

DEFAULT_STATE = {
    "language": "en",
    "library": [],
    "current_track_index": None,
    "current_track": None,
    "eq_preset": "Classic",
    "speed_preset": "Normal",
    "background": {"type": "gradient", "value": ""},
    "tokens": {field: "" for field, _label in TOKEN_FIELDS},
    "play_history": [],
    "custom_waves": [],
    "favorites": [],
    "playlists": [],
    "custom_eq": {"low": 0, "mid": 0, "high": 0},
}

TRANSLATIONS = {
    "en": {
        "app_name": "PulseDock Studio",
        "player": "Player",
        "options": "Options",
        "arcade": "Arcade",
        "server": "Server",
        "language": "Language",
        "import_tracks": "Import tracks",
        "current_track": "Current track",
        "library": "Library",
        "search": "Search",
        "search_platforms": "Search platforms",
        "search_placeholder": "Track, artist, album, or mood",
        "lyrics": "Lyrics",
        "open_text": "Open text source",
        "open_music": "Open music",
        "open_all": "Open all",
        "select": "Select",
        "play": "Play",
        "pause": "Pause",
        "stop": "Stop",
        "equalizer": "Equalizer",
        "speed": "Playback mode",
        "backgrounds": "Background studio",
        "choose_file": "Choose file",
        "apply_source": "Apply source",
        "reset_background": "Reset background",
        "source_placeholder": "Paste local path, direct URL, or data:image",
        "tokens": "API tokens",
        "save_tokens": "Save tokens",
        "save_settings": "Save settings",
        "status_ready": "Embedded server running",
        "status_demo": "Playback demo mode: install python-vlc and VLC for audio output",
        "empty_library": "Import MP3, WAV, FLAC, OGG, or M4A files to build the local player.",
        "empty_results": "Search to generate Spotify, YouTube Music, SoundCloud, and TuneMyMusic shortcuts.",
        "background_hint": "GIF animation works in preview when Tk can decode the file.",
        "server_note": "The local server exposes JSON and media endpoints only. No browser site is required.",
        "mini_spots": "Spots",
        "mini_snake": "Snake",
        "mini_calc": "Calculator",
        "start": "Start",
        "reset": "Reset",
        "score": "Score",
        "best": "Best",
    },
    "ru": {
        "app_name": "PulseDock Studio",
        "player": "Плеер",
        "options": "Опции",
        "arcade": "Аркада",
        "server": "Сервер",
        "language": "Язык",
        "import_tracks": "Импорт треков",
        "current_track": "Текущий трек",
        "library": "Библиотека",
        "search": "Поиск",
        "search_platforms": "Искать в сервисах",
        "search_placeholder": "Трек, артист, альбом или настроение",
        "lyrics": "Текст",
        "open_text": "Открыть источник текста",
        "open_music": "Открыть музыку",
        "open_all": "Открыть всё",
        "select": "Выбрать",
        "play": "Играть",
        "pause": "Пауза",
        "stop": "Стоп",
        "equalizer": "Эквалайзер",
        "speed": "Режим скорости",
        "backgrounds": "Фоны",
        "choose_file": "Выбрать файл",
        "apply_source": "Применить источник",
        "reset_background": "Сбросить фон",
        "source_placeholder": "Вставьте локальный путь, прямой URL или data:image",
        "tokens": "API токены",
        "save_tokens": "Сохранить токены",
        "save_settings": "Сохранить настройки",
        "status_ready": "Встроенный сервер запущен",
        "status_demo": "Режим демо: установите python-vlc и VLC для вывода звука",
        "empty_library": "Импортируйте MP3, WAV, FLAC, OGG или M4A для локального плеера.",
        "empty_results": "Введите запрос, чтобы получить ссылки Spotify, YouTube Music, SoundCloud и TuneMyMusic.",
        "background_hint": "Анимация GIF работает в превью, если Tk может декодировать файл.",
        "server_note": "Локальный сервер отдаёт только JSON и медиа-точки. Сайт в браузере не нужен.",
        "mini_spots": "Точки",
        "mini_snake": "Змейка",
        "mini_calc": "Калькулятор",
        "start": "Старт",
        "reset": "Сброс",
        "score": "Счёт",
        "best": "Рекорд",
    },
}


def build_default_state() -> dict:
    return deepcopy(DEFAULT_STATE)


def merge_nested(defaults: dict, loaded: dict) -> dict:
    merged = deepcopy(defaults)
    for key, value in loaded.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def sync_current_track(state: dict) -> None:
    library = state.get("library", [])
    index = state.get("current_track_index")
    if isinstance(index, int) and 0 <= index < len(library):
        state["current_track"] = library[index]
        return

    current_track = state.get("current_track")
    if isinstance(current_track, dict):
        current_path = str(current_track.get("path", ""))
        for item_index, item in enumerate(library):
            if current_path and str(item.get("path", "")) == current_path:
                state["current_track_index"] = item_index
                state["current_track"] = item
                return

    state["current_track_index"] = None
    state["current_track"] = None


def load_state() -> dict:
    state = build_default_state()
    if DATA_FILE.exists():
        try:
            loaded = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                state = merge_nested(state, loaded)
        except Exception:
            pass
    state["library"] = [item for item in state.get("library", []) if isinstance(item, dict)]
    state["tokens"] = merge_nested(DEFAULT_STATE["tokens"], state.get("tokens", {}))
    sanitize_history(state)
    sync_current_track(state)
    return state


def save_state(state: dict) -> None:
    sync_current_track(state)
    DATA_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def set_current_track(state: dict, index: int | None) -> None:
    state["current_track_index"] = index
    sync_current_track(state)


def get_ui(state: dict) -> dict:
    language = state.get("language", "en")
    return TRANSLATIONS["ru"] if language == "ru" else TRANSLATIONS["en"]


def unique_target(directory: Path, filename: str, fallback_stem: str = "media") -> Path:
    safe_name = secure_filename(filename) or fallback_stem
    stem = Path(safe_name).stem or fallback_stem
    suffix = Path(safe_name).suffix
    candidate = directory / f"{stem}{suffix}"
    counter = 1
    while candidate.exists():
        candidate = directory / f"{stem}-{counter}{suffix}"
        counter += 1
    return candidate


def infer_extension_from_content_type(content_type: str) -> str:
    if not content_type:
        return ".bin"
    guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
    return guessed or ".bin"


def import_track_path(path_value: str) -> dict:
    path = Path(path_value)
    if not path.exists() or not path.is_file():
        raise ValueError("Track file not found.")
    target = unique_target(TRACKS_DIR, path.name, "track")
    shutil.copy2(path, target)
    return {
        "title": target.stem.replace("-", " ").replace("_", " "),
        "path": str(target.resolve()),
        "relative_path": target.name,
        "source": "Local Upload",
    }


def import_background_source(raw_value: str) -> str:
    value = raw_value.strip().strip('"').strip("'")
    if not value:
        raise ValueError("No background source provided.")

    local_path = Path(value)
    if local_path.exists() and local_path.is_file():
        target = unique_target(BACKGROUNDS_DIR, local_path.name, "background")
        shutil.copy2(local_path, target)
        return target.name

    if value.startswith("data:image/"):
        header, _, payload = value.partition(",")
        if not payload:
            raise ValueError("Invalid data image.")
        is_base64 = ";base64" in header
        media_type = header[5:].split(";")[0]
        suffix = infer_extension_from_content_type(media_type)
        target = unique_target(BACKGROUNDS_DIR, f"pasted{suffix}", "background")
        try:
            data = base64.b64decode(payload) if is_base64 else payload.encode("utf-8")
        except binascii.Error as exc:
            raise ValueError("Invalid base64 image data.") from exc
        target.write_bytes(data)
        return target.name

    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        with urlopen(value, timeout=12) as response:
            content_type = response.headers.get("Content-Type", "")
            suffix = Path(parsed.path).suffix or infer_extension_from_content_type(content_type)
            target = unique_target(BACKGROUNDS_DIR, f"remote{suffix}", "background")
            target.write_bytes(response.read())
        return target.name

    raise ValueError("Unsupported background source.")


def resolve_background_path(state: dict) -> Path | None:
    background = state.get("background", {})
    if background.get("type") != "upload":
        return None
    value = str(background.get("value", "")).strip()
    if not value:
        return None
    path = BACKGROUNDS_DIR / value
    return path if path.exists() else None


def track_source_path(item: dict) -> Path:
    relative_path = item.get("relative_path")
    if relative_path:
        return TRACKS_DIR / str(relative_path)
    return Path(str(item.get("path", "")))


def build_search_results(query: str) -> list[dict]:
    if not query:
        return []
    encoded = quote_plus(query)
    return [
        {
            "provider": provider["name"],
            "url": provider["url"].format(query=encoded),
            "text_url": LYRICS_SOURCES[0]["url"].format(query=encoded),
            "hint": provider["text_hint"],
        }
        for provider in PROVIDERS
    ]


def build_lyrics_links(query: str) -> list[dict]:
    if not query:
        return []
    encoded = quote_plus(query)
    return [{"name": item["name"], "url": item["url"].format(query=encoded)} for item in LYRICS_SOURCES]


STOP_WORDS = {
    "the", "and", "feat", "with", "from", "radio", "mix", "edit", "version", "live", "remix",
    "track", "song", "official", "audio", "video", "prod", "dj", "mc", "a", "an",
}


def sanitize_history(state: dict) -> None:
    history = state.get("play_history", [])
    waves = state.get("custom_waves", [])
    state["play_history"] = [item for item in history if isinstance(item, dict)]
    state["custom_waves"] = [item for item in waves if isinstance(item, dict)]
    state["favorites"] = [item for item in state.get("favorites", []) if isinstance(item, str)]
    state["playlists"] = [item for item in state.get("playlists", []) if isinstance(item, dict)]
    custom_eq = state.get("custom_eq", {})
    if not isinstance(custom_eq, dict):
        custom_eq = {}
    state["custom_eq"] = {
        "low": int(custom_eq.get("low", 0)),
        "mid": int(custom_eq.get("mid", 0)),
        "high": int(custom_eq.get("high", 0)),
    }


def normalize_track_title(title: str) -> str:
    cleaned = " ".join(str(title).replace("_", " ").replace("-", " ").split())
    return cleaned.strip()


def get_track_key(track: dict) -> str:
    return str(track.get("relative_path") or track.get("path") or track.get("title") or "").strip()


def tokenize_title(title: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9']+", normalize_track_title(title).lower())
    return [token for token in tokens if len(token) > 2 and token not in STOP_WORDS]


def record_play_event(state: dict, track: dict) -> None:
    title = normalize_track_title(track.get("title", ""))
    if not title:
        return
    history = state.setdefault("play_history", [])
    history.append({"title": title, "source": track.get("source", "Local")})
    if len(history) > 40:
        del history[:-40]


def toggle_favorite(state: dict, track: dict) -> bool:
    track_key = get_track_key(track)
    favorites = list(state.get("favorites", []))
    if track_key in favorites:
        favorites.remove(track_key)
        state["favorites"] = favorites
        return False
    favorites.append(track_key)
    state["favorites"] = favorites
    return True


def is_favorite(state: dict, track: dict) -> bool:
    return get_track_key(track) in state.get("favorites", [])


def create_playlist(state: dict, name: str) -> None:
    playlist_name = " ".join(name.split())
    if not playlist_name:
        raise ValueError("Playlist name is required.")
    playlists = [item for item in state.get("playlists", []) if item.get("name", "").lower() != playlist_name.lower()]
    playlists.append({"name": playlist_name, "tracks": []})
    state["playlists"] = playlists


def add_track_to_playlist(state: dict, playlist_name: str, track: dict) -> None:
    playlist_key = playlist_name.strip().lower()
    if not playlist_key:
        raise ValueError("Select a playlist first.")
    track_key = get_track_key(track)
    if not track_key:
        raise ValueError("Invalid track.")
    for playlist in state.get("playlists", []):
        if playlist.get("name", "").lower() == playlist_key:
            tracks = playlist.setdefault("tracks", [])
            if track_key not in tracks:
                tracks.append(track_key)
            return
    raise ValueError("Playlist not found.")


def remove_track_from_playlist(state: dict, playlist_name: str, track_key: str) -> None:
    playlist_key = playlist_name.strip().lower()
    for playlist in state.get("playlists", []):
        if playlist.get("name", "").lower() == playlist_key:
            playlist["tracks"] = [item for item in playlist.get("tracks", []) if item != track_key]
            return


def save_custom_wave(state: dict, name: str, keywords: str) -> None:
    wave_name = " ".join(name.split())
    keyword_text = " ".join(keywords.split())
    if not wave_name or not keyword_text:
        raise ValueError("Wave name and keywords are required.")
    wave = {"name": wave_name, "keywords": keyword_text}
    waves = [item for item in state.get("custom_waves", []) if item.get("name", "").lower() != wave_name.lower()]
    waves.insert(0, wave)
    state["custom_waves"] = waves[:12]


def build_recommendation_foundation(state: dict, selected_wave: str = "") -> dict:
    sanitize_history(state)
    history = state.get("play_history", [])
    library = state.get("library", [])
    waves = state.get("custom_waves", [])
    recent_titles: list[str] = []
    for item in reversed(history):
        title = normalize_track_title(item.get("title", ""))
        if title and title not in recent_titles:
            recent_titles.append(title)
        if len(recent_titles) >= 5:
            break
    if not recent_titles:
        for item in library[-5:]:
            title = normalize_track_title(item.get("title", ""))
            if title and title not in recent_titles:
                recent_titles.append(title)

    keyword_scores: dict[str, int] = {}
    for item in history[-12:]:
        for token in tokenize_title(item.get("title", "")):
            keyword_scores[token] = keyword_scores.get(token, 0) + 2
    for item in library[-10:]:
        for token in tokenize_title(item.get("title", "")):
            keyword_scores[token] = keyword_scores.get(token, 0) + 1
    top_keywords = [token for token, _score in sorted(keyword_scores.items(), key=lambda item: (-item[1], item[0]))[:6]]

    active_wave = None
    for wave in waves:
        if wave.get("name", "").lower() == selected_wave.lower():
            active_wave = wave
            break
    if active_wave is None and waves:
        active_wave = waves[0]

    suggestions: list[dict] = []
    for title in recent_titles[:3]:
        suggestions.append({"label": title, "query": title, "reason": "recent favorite"})
        suggestions.append({"label": f"{title} live", "query": f"{title} live", "reason": "based on recent listening"})
    if top_keywords:
        suggestions.append(
            {
                "label": "Keyword mix",
                "query": " ".join(top_keywords[:3]),
                "reason": "built from the strongest repeated words in your listening history",
            }
        )
    if active_wave:
        suggestions.append(
            {
                "label": active_wave["name"],
                "query": active_wave["keywords"],
                "reason": f"custom wave: {active_wave['name']}",
            }
        )
        if recent_titles:
            suggestions.append(
                {
                    "label": f"{active_wave['name']} blend",
                    "query": f"{recent_titles[0]} {active_wave['keywords']}",
                    "reason": "mix of your latest track and the active wave",
                }
            )

    deduped: list[dict] = []
    seen_queries: set[str] = set()
    for item in suggestions:
        query = item["query"].strip()
        lowered = query.lower()
        if not query or lowered in seen_queries:
            continue
        seen_queries.add(lowered)
        deduped.append(item)

    return {
        "recent_titles": recent_titles,
        "top_keywords": top_keywords,
        "waves": waves,
        "active_wave": active_wave,
        "suggestions": deduped[:8],
    }


api = Flask(__name__)


@api.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@api.get("/api/state")
def state_snapshot():
    state = load_state()
    return jsonify(
        {
            "language": state.get("language"),
            "current_track": state.get("current_track"),
            "library_count": len(state.get("library", [])),
            "eq_preset": state.get("eq_preset"),
            "speed_preset": state.get("speed_preset"),
            "background": state.get("background"),
        }
    )


@api.get("/api/search/<path:query>")
def search(query: str):
    return jsonify({"query": query, "results": build_search_results(query), "lyrics": build_lyrics_links(query)})


@api.get("/media/backgrounds/<path:filename>")
def background_media(filename: str):
    return send_from_directory(BACKGROUNDS_DIR, filename)


@api.get("/media/tracks/<int:track_id>")
def media_track(track_id: int):
    state = load_state()
    library = state.get("library", [])
    if track_id < 0 or track_id >= len(library):
        abort(404)
    path = track_source_path(library[track_id])
    if not path.exists():
        abort(404)
    return send_file(path)


class EmbeddedServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 5055) -> None:
        self.host = host
        self.port = port
        self._server = make_server(host, port, api, threaded=True)
        self._thread = threading.Thread(target=self._server.serve_forever, name="PulseDockServer", daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._thread.join(timeout=2)
