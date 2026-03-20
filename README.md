# PulseDock Studio

Desktop music app with an embedded local server. No browser site is required.

## Features

- native Tkinter desktop app
- embedded local JSON/media server
- local track import and playback shell
- Spotify, YouTube Music, SoundCloud, and TuneMyMusic shortcuts
- RU / EN language setting
- equalizer and playback speed presets
- background import from file, URL, or `data:image`
- local token storage for future API integrations
- recommendation foundation based on listening history and custom user waves
- separate library views for tracks, favourite tracks, and playlists
- hand-customized EQ mode plus Rock, Club, and Studio presets
- official Spotify / SoundCloud / YouTube pages open inside an embedded app window
- official embed portal for pasted Spotify / SoundCloud / YouTube URLs
- mini games: Spots, Snake, Calculator

## Run app

```bash
python main.py
```

## Run server only

```bash
python main.py server
```

## JavaScript equalizer

Open `web_equalizer.html` in a browser.

- standalone Web Audio API equalizer
- 10 bands
- presets: Flat, Rock, Club, Studio, BassBoost, Vocal
- local audio file input

## Embedded music window

- `Open music` now opens official provider pages in an embedded app window
- `Open Embed Portal` opens a tool for pasted Spotify, SoundCloud, and YouTube URLs
- local files stay in the native player

## Install dependencies

```bash
pip install -r requirements.txt
```

## Notes

- The embedded server exposes API/media endpoints for local app use. It does not serve a website.
- Search actions open official platform pages instead of bypassing Spotify, YouTube Music, SoundCloud, or TuneMyMusic restrictions.
- Automatic lyrics or metadata import from Spotify / YouTube Music is still not implemented because that requires official APIs and credentials.
