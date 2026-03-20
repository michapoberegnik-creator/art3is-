from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path
from urllib.parse import quote_plus

from flask import Flask, abort, flash, redirect, render_template, request, send_file, send_from_directory, url_for
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
]

LYRICS_SOURCES = [
    {
        "name": "Genius",
        "url": "https://genius.com/search?q={query}",
    },
    {
        "name": "YouTube",
        "url": "https://www.youtube.com/results?search_query={query}+lyrics",
    },
]

EQ_PRESETS = {
    "Flat": {"low": 0, "mid": 0, "high": 0},
    "Classic": {"low": 1, "mid": 2, "high": 3},
    "Bass Boost": {"low": 7, "mid": 1, "high": -1},
    "Vocal": {"low": -2, "mid": 5, "high": 2},
    "Treble Lift": {"low": -1, "mid": 1, "high": 6},
    "Night Mode": {"low": 2, "mid": 0, "high": -4},
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
    "background": {
        "type": "gradient",
        "value": "",
    },
    "tokens": {field: "" for field, _label in TOKEN_FIELDS},
}

TRANSLATIONS = {
    "en": {
        "app_name": "PulseDock Studio",
        "tagline": "Minimal dark music workspace with search routing, local playback, themes, and side arcade tools.",
        "hero_note": "Spotify, SoundCloud, and YouTube Music stay linked through official search pages. Local audio remains playable inside the project.",
        "search_placeholder": "Track, artist, album, or mood",
        "search_button": "Search platforms",
        "upload_tracks": "Import local tracks",
        "current_track": "Current track",
        "no_track": "No local track selected yet.",
        "library": "Local library",
        "platform_results": "Platform results",
        "recommendations": "Search ideas",
        "lyrics": "Lyrics and text shortcuts",
        "lyrics_note": "Direct lyrics or metadata import from Spotify and YouTube Music requires official APIs or licensed providers. This project keeps the workflow compliant and opens official destinations.",
        "options": "Options",
        "appearance": "Appearance",
        "language": "Language",
        "audio_lab": "Audio lab",
        "equalizer": "Equalizer",
        "speed": "Playback mode",
        "save_audio": "Save audio settings",
        "tokens": "API tokens",
        "save_tokens": "Save token fields",
        "backgrounds": "Background studio",
        "upload_background": "Upload image or GIF",
        "set_background_url": "Use image / GIF URL",
        "paste_background": "Paste URL, data image, or local file path",
        "apply_background": "Apply background",
        "reset_background": "Reset to animated gradient",
        "background_hint": "Upload from disk, paste a direct URL, paste a data:image value, or paste a local file path so the app can import it.",
        "arcade": "Mini arcade",
        "spots": "Spots",
        "snake": "Snake",
        "calculator": "Calculator",
        "start": "Start",
        "reset": "Reset",
        "score": "Score",
        "best": "Best",
        "select": "Select",
        "play_local": "Play local",
        "open": "Open",
        "listen": "Open music",
        "text_view": "Open text source",
        "save_language": "Save language",
        "background_mode": "Current background",
        "query_caption": "Prepared around your current query.",
        "token_note": "These fields are stored locally for future official API integrations.",
        "empty_library": "Import MP3, WAV, FLAC, OGG, or M4A files to build the local player.",
        "empty_results": "Search to generate official shortcuts for Spotify, YouTube Music, and SoundCloud.",
        "empty_recommendations": "Search to generate follow-up prompts like remix, acoustic, or slowed versions.",
        "current_background_gradient": "Animated gradient",
    },
    "ru": {
        "app_name": "PulseDock Studio",
        "tagline": "Минималистичное тёмное музыкальное пространство с поиском, локальным плеером, темами и мини-играми.",
        "hero_note": "Spotify, SoundCloud и YouTube Music открываются через официальные страницы поиска. Локальные треки воспроизводятся прямо в проекте.",
        "search_placeholder": "Трек, артист, альбом или настроение",
        "search_button": "Искать в сервисах",
        "upload_tracks": "Импортировать локальные треки",
        "current_track": "Текущий трек",
        "no_track": "Локальный трек пока не выбран.",
        "library": "Локальная библиотека",
        "platform_results": "Результаты по сервисам",
        "recommendations": "Идеи для поиска",
        "lyrics": "Текст и ссылки",
        "lyrics_note": "Прямой импорт текста или метаданных из Spotify и YouTube Music требует официальных API или лицензированного провайдера. Этот проект оставляет процесс легальным и открывает официальные страницы.",
        "options": "Опции",
        "appearance": "Оформление",
        "language": "Язык",
        "audio_lab": "Аудио",
        "equalizer": "Эквалайзер",
        "speed": "Режим скорости",
        "save_audio": "Сохранить аудио-настройки",
        "tokens": "API токены",
        "save_tokens": "Сохранить токены",
        "backgrounds": "Фоны",
        "upload_background": "Загрузить изображение или GIF",
        "set_background_url": "Использовать URL изображения / GIF",
        "paste_background": "Вставить URL, data image или локальный путь",
        "apply_background": "Применить фон",
        "reset_background": "Сбросить на анимированный градиент",
        "background_hint": "Можно загрузить файл с диска, вставить прямой URL, data:image или локальный путь, чтобы приложение импортировало фон.",
        "arcade": "Мини-аркада",
        "spots": "Точки",
        "snake": "Змейка",
        "calculator": "Калькулятор",
        "start": "Старт",
        "reset": "Сброс",
        "score": "Счёт",
        "best": "Рекорд",
        "select": "Выбрать",
        "play_local": "Играть локально",
        "open": "Открыть",
        "listen": "Открыть музыку",
        "text_view": "Открыть текстовый источник",
        "save_language": "Сохранить язык",
        "background_mode": "Текущий фон",
        "query_caption": "Подготовлено под текущий запрос.",
        "token_note": "Эти поля хранятся локально для будущих официальных интеграций API.",
        "empty_library": "Импортируйте MP3, WAV, FLAC, OGG или M4A, чтобы собрать локальный плеер.",
        "empty_results": "Введите запрос, чтобы создать официальные ссылки для Spotify, YouTube Music и SoundCloud.",
        "empty_recommendations": "Введите запрос, чтобы получить идеи вроде remix, acoustic или slowed.",
        "current_background_gradient": "Анимированный градиент",
    },
}


app = Flask(__name__, template_folder=str(APP_DIR / "templates"))
app.secret_key = "pulsedock-local-ui"


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
    sync_current_track(state)
    return state


def save_state(state: dict) -> None:
    sync_current_track(state)
    DATA_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


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


def set_current_track(state: dict, index: int | None) -> None:
    state["current_track_index"] = index
    sync_current_track(state)


def get_language(state: dict) -> str:
    language = state.get("language", "en")
    if language not in TRANSLATIONS:
        return "en"
    return language


def get_ui(state: dict) -> dict:
    return TRANSLATIONS[get_language(state)]


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


def build_recommendations(query: str) -> list[str]:
    if not query:
        return []
    return [
        f"{query} live session",
        f"{query} acoustic",
        f"{query} remix",
        f"{query} slowed",
        f"{query} sped up",
        f"{query} instrumental",
    ]


def build_lyrics_links(query: str) -> list[dict]:
    if not query:
        return []
    encoded = quote_plus(query)
    return [{"name": item["name"], "url": item["url"].format(query=encoded)} for item in LYRICS_SOURCES]


def build_background_preview(state: dict) -> str | None:
    background = state.get("background", {})
    bg_type = background.get("type", "gradient")
    value = str(background.get("value", "")).strip()
    if bg_type == "upload" and value:
        return url_for("background_media", filename=value)
    if bg_type in {"url", "pasted"} and value:
        return value
    return None


def get_background_label(state: dict) -> str:
    ui = get_ui(state)
    background = state.get("background", {})
    bg_type = background.get("type", "gradient")
    if bg_type == "upload":
        return f"Upload: {background.get('value', '')}"
    if bg_type == "url":
        return "Remote URL"
    if bg_type == "pasted":
        return "Pasted media"
    return ui["current_background_gradient"]


def unique_target(directory: Path, filename: str) -> Path:
    safe_name = secure_filename(filename) or "media.bin"
    base = Path(safe_name).stem or "media"
    suffix = Path(safe_name).suffix or ".bin"
    candidate = directory / f"{base}{suffix}"
    counter = 1
    while candidate.exists():
        candidate = directory / f"{base}-{counter}{suffix}"
        counter += 1
    return candidate


def save_uploaded_file(storage, directory: Path) -> Path:
    target = unique_target(directory, storage.filename)
    storage.save(target)
    return target


def import_background_path(raw_path: str) -> str | None:
    cleaned = raw_path.strip().strip('"').strip("'")
    if not cleaned:
        return None
    path = Path(cleaned)
    if not path.exists() or not path.is_file():
        return None
    target = unique_target(BACKGROUNDS_DIR, path.name)
    shutil.copy2(path, target)
    return target.name


def track_source_path(item: dict) -> Path:
    relative_path = item.get("relative_path")
    if relative_path:
        return TRACKS_DIR / str(relative_path)
    return Path(str(item.get("path", "")))


def flash_for_language(state: dict, en_message: str, ru_message: str) -> None:
    flash(ru_message if get_language(state) == "ru" else en_message)


@app.get("/")
def index():
    state = load_state()
    query = request.args.get("q", "").strip()
    if not query and state.get("current_track"):
        query = str(state["current_track"].get("title", "")).strip()

    return render_template(
        "index.html",
        ui=get_ui(state),
        state=state,
        query=query,
        search_results=build_search_results(query),
        recommendations=build_recommendations(query),
        lyrics_links=build_lyrics_links(query),
        background_url=build_background_preview(state),
        background_label=get_background_label(state),
        current_track=state.get("current_track"),
        current_track_index=state.get("current_track_index"),
        eq_presets=list(EQ_PRESETS.keys()),
        speed_presets=list(SPEED_PRESETS.keys()),
        eq_profiles=EQ_PRESETS,
        speed_values=SPEED_PRESETS,
        token_fields=TOKEN_FIELDS,
    )


@app.post("/library/upload")
def upload_tracks():
    state = load_state()
    files = [item for item in request.files.getlist("tracks") if item and item.filename]
    added_indices: list[int] = []
    for storage in files:
        target = save_uploaded_file(storage, TRACKS_DIR)
        state["library"].append(
            {
                "title": target.stem.replace("-", " ").replace("_", " "),
                "path": str(target.resolve()),
                "relative_path": target.name,
                "source": "Local Upload",
            }
        )
        added_indices.append(len(state["library"]) - 1)

    if added_indices:
        set_current_track(state, added_indices[0])
        save_state(state)
        flash_for_language(state, f"Imported {len(added_indices)} track(s).", f"Импортировано треков: {len(added_indices)}.")
    else:
        flash_for_language(state, "No files were selected.", "Файлы не выбраны.")

    return redirect(url_for("index"))


@app.post("/library/select/<int:track_id>")
def select_track(track_id: int):
    state = load_state()
    if track_id < 0 or track_id >= len(state["library"]):
        abort(404)
    set_current_track(state, track_id)
    save_state(state)
    flash_for_language(state, "Current track updated.", "Текущий трек обновлён.")
    return redirect(url_for("index"))


@app.post("/settings/language")
def update_language():
    state = load_state()
    language = request.form.get("language", "en").strip()
    state["language"] = language if language in TRANSLATIONS else "en"
    save_state(state)
    flash_for_language(state, "Language updated.", "Язык обновлён.")
    return redirect(url_for("index"))


@app.post("/settings/audio")
def update_audio():
    state = load_state()
    eq_preset = request.form.get("eq_preset", state["eq_preset"]).strip()
    speed_preset = request.form.get("speed_preset", state["speed_preset"]).strip()
    if eq_preset in EQ_PRESETS:
        state["eq_preset"] = eq_preset
    if speed_preset in SPEED_PRESETS:
        state["speed_preset"] = speed_preset
    save_state(state)
    flash_for_language(state, "Audio settings saved.", "Аудио-настройки сохранены.")
    return redirect(url_for("index"))


@app.post("/settings/tokens")
def update_tokens():
    state = load_state()
    for field, _label in TOKEN_FIELDS:
        state["tokens"][field] = request.form.get(field, "").strip()
    save_state(state)
    flash_for_language(state, "Token fields saved locally.", "Поля токенов сохранены локально.")
    return redirect(url_for("index"))


@app.post("/settings/background")
def update_background():
    state = load_state()
    mode = request.form.get("mode", "").strip()

    if mode == "reset":
        state["background"] = {"type": "gradient", "value": ""}
        save_state(state)
        flash_for_language(state, "Background reset to animated gradient.", "Фон сброшен на анимированный градиент.")
        return redirect(url_for("index"))

    if mode == "upload":
        storage = request.files.get("background_file")
        if storage and storage.filename:
            target = save_uploaded_file(storage, BACKGROUNDS_DIR)
            state["background"] = {"type": "upload", "value": target.name}
            save_state(state)
            flash_for_language(state, "Background uploaded.", "Фон загружен.")
        else:
            flash_for_language(state, "Choose an image or GIF first.", "Сначала выберите изображение или GIF.")
        return redirect(url_for("index"))

    if mode == "url":
        raw_url = request.form.get("background_url", "").strip()
        if raw_url.startswith(("http://", "https://", "data:image/")):
            state["background"] = {"type": "url", "value": raw_url}
            save_state(state)
            flash_for_language(state, "Background URL applied.", "URL фона применён.")
        else:
            flash_for_language(state, "Use a direct http(s) URL or data:image value.", "Используйте прямой URL http(s) или data:image.")
        return redirect(url_for("index"))

    if mode == "paste":
        pasted = request.form.get("background_paste", "").strip()
        imported_name = import_background_path(pasted)
        if imported_name:
            state["background"] = {"type": "upload", "value": imported_name}
            save_state(state)
            flash_for_language(state, "Local background imported from pasted path.", "Локальный фон импортирован из вставленного пути.")
        elif pasted.startswith(("http://", "https://", "data:image/")):
            state["background"] = {"type": "pasted", "value": pasted}
            save_state(state)
            flash_for_language(state, "Pasted background applied.", "Вставленный фон применён.")
        else:
            flash_for_language(state, "Paste a valid URL, data image, or local file path.", "Вставьте корректный URL, data image или локальный путь к файлу.")
        return redirect(url_for("index"))

    flash_for_language(state, "Unknown background action.", "Неизвестное действие для фона.")
    return redirect(url_for("index"))


@app.get("/stream/<int:track_id>")
def stream(track_id: int):
    state = load_state()
    library = state.get("library", [])
    if track_id < 0 or track_id >= len(library):
        abort(404)
    path = track_source_path(library[track_id])
    if not path.exists():
        abort(404)
    return send_file(path)


@app.get("/media/backgrounds/<path:filename>")
def background_media(filename: str):
    return send_from_directory(BACKGROUNDS_DIR, filename)


def run_web_app() -> None:
    app.run(debug=False, host="127.0.0.1", port=5055)
