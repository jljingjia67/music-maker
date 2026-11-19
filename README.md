# Lyric Video Generator

Uses OpenAI Whisper to transcribe a song and generates a karaoke-style lyric video with synced text overlay.

## Setup

```bash
pip install -r requirements.txt
```

You also need `ffmpeg` installed:

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

## Usage

### Basic usage

```bash
python lyric_video.py song.mp3
```

This transcribes the song with Whisper and outputs `lyric_video.mp4`.

### Use a larger Whisper model for better accuracy

```bash
python lyric_video.py song.mp3 -m medium
```

Model sizes: `tiny`, `base`, `small`, `medium`, `large` (larger = slower but more accurate).

### Custom output and styling

```bash
python lyric_video.py song.mp3 \
  -o my_video.mp4 \
  --font-size 70 \
  --highlight-color "#FF69B4" \
  --bg-color "0,0,0" \
  --words-per-line 6
```

### Save and reuse transcripts

```bash
# Transcribe only
python lyric_video.py song.mp3 --transcript-only --save-transcript lyrics.json

# Generate video from saved transcript (skip re-transcription)
python lyric_video.py song.mp3 --transcript lyrics.json -o video.mp4
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `-o, --output` | `lyric_video.mp4` | Output video path |
| `-m, --model` | `base` | Whisper model size |
| `--width` | `1920` | Video width |
| `--height` | `1080` | Video height |
| `--font-size` | `60` | Lyric font size |
| `--font` | `Arial-Bold` | Font name |
| `--bg-color` | `15,15,30` | Background color (R,G,B) |
| `--text-color` | `white` | Lyric text color |
| `--highlight-color` | `#00BFFF` | Karaoke highlight color |
| `--words-per-line` | `8` | Max words per line |
| `--transcript` | — | Load saved transcript JSON |
| `--save-transcript` | — | Save transcript to JSON |
| `--transcript-only` | — | Only transcribe, skip video |
