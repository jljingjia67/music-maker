#!/usr/bin/env python3
"""
Lyric Video Generator
Takes a song audio file, transcribes it with AI (Whisper),
and generates a video with synced lyric overlay.
"""

import argparse
import json
import os
import sys
import textwrap
from pathlib import Path

import whisper
from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeVideoClip,
    TextClip,
    concatenate_videoclips,
)


def transcribe_song(audio_path: str, model_size: str = "base") -> dict:
    """Transcribe the song using Whisper with word-level timestamps."""
    print(f"Loading Whisper model '{model_size}'...")
    model = whisper.load_model(model_size)

    print(f"Transcribing '{audio_path}'...")
    result = model.transcribe(
        audio_path,
        word_timestamps=True,
        language="en",
    )

    segments = []
    for seg in result["segments"]:
        words = []
        if "words" in seg:
            for w in seg["words"]:
                words.append({
                    "word": w["word"].strip(),
                    "start": w["start"],
                    "end": w["end"],
                })
        segments.append({
            "text": seg["text"].strip(),
            "start": seg["start"],
            "end": seg["end"],
            "words": words,
        })

    return {"text": result["text"], "segments": segments}


def group_into_lines(segments: list[dict], max_words_per_line: int = 8) -> list[dict]:
    """Group word-level timestamps into display lines."""
    lines = []
    for seg in segments:
        if not seg["words"]:
            lines.append({
                "text": seg["text"],
                "start": seg["start"],
                "end": seg["end"],
                "words": [],
            })
            continue

        current_words = []
        for word_info in seg["words"]:
            current_words.append(word_info)
            if len(current_words) >= max_words_per_line:
                text = " ".join(w["word"] for w in current_words)
                lines.append({
                    "text": text,
                    "start": current_words[0]["start"],
                    "end": current_words[-1]["end"],
                    "words": list(current_words),
                })
                current_words = []

        if current_words:
            text = " ".join(w["word"] for w in current_words)
            lines.append({
                "text": text,
                "start": current_words[0]["start"],
                "end": current_words[-1]["end"],
                "words": list(current_words),
            })

    return lines


def create_lyric_video(
    audio_path: str,
    transcript: dict,
    output_path: str = "lyric_video.mp4",
    resolution: tuple[int, int] = (1920, 1080),
    font_size: int = 60,
    font: str = "Arial-Bold",
    bg_color: tuple[int, int, int] = (15, 15, 30),
    text_color: str = "white",
    highlight_color: str = "#00BFFF",
    max_words_per_line: int = 8,
):
    """Generate the lyric video with animated text overlay."""
    width, height = resolution
    lines = group_into_lines(transcript["segments"], max_words_per_line)

    audio = AudioFileClip(audio_path)
    duration = audio.duration

    background = ColorClip(size=resolution, color=bg_color).with_duration(duration)

    title_name = Path(audio_path).stem.replace("_", " ").replace("-", " ").title()
    title_clip = (
        TextClip(
            text=title_name,
            font_size=font_size + 10,
            color=text_color,
            font=font,
            text_align="center",
        )
        .with_position(("center", height // 6))
        .with_start(0)
        .with_duration(min(4.0, lines[0]["start"] if lines else 4.0))
        .with_effects([lambda clip: clip.crossfadein(0.5), lambda clip: clip.crossfadeout(0.5)])
    )

    lyric_clips = []
    for i, line in enumerate(lines):
        fade_in = 0.2
        fade_out = 0.3
        padding = 0.1
        start = max(0, line["start"] - padding)
        end = line["end"] + padding

        line_duration = end - start
        if line_duration <= 0:
            continue

        lyric_clip = (
            TextClip(
                text=line["text"],
                font_size=font_size,
                color=text_color,
                font=font,
                text_align="center",
                stroke_color="black",
                stroke_width=2,
            )
            .with_position(("center", height * 0.45))
            .with_start(start)
            .with_duration(line_duration)
        )
        lyric_clips.append(lyric_clip)

        if line["words"]:
            elapsed = 0
            for w in line["words"]:
                word_start = w["start"]
                word_end = line["end"] + padding
                word_duration = word_end - word_start
                if word_duration <= 0:
                    continue

                progress_text = line["text"]
                highlighted_words = []
                for ww in line["words"]:
                    if ww["start"] <= w["start"]:
                        highlighted_words.append(ww["word"])

                highlight_text = " ".join(highlighted_words)

                highlight_clip = (
                    TextClip(
                        text=highlight_text,
                        font_size=font_size,
                        color=highlight_color,
                        font=font,
                        text_align="left",
                        stroke_color="black",
                        stroke_width=2,
                    )
                    .with_start(word_start)
                    .with_duration(max(0.05, w["end"] - w["start"]))
                )

                try:
                    full_width = lyric_clip.size[0]
                    highlight_width = highlight_clip.size[0]
                    x_offset = (width - full_width) // 2
                    highlight_clip = highlight_clip.with_position(
                        (x_offset, height * 0.45)
                    )
                    lyric_clips.append(highlight_clip)
                except Exception:
                    pass

        if i < len(lines) - 1:
            next_start = lines[i + 1]["start"]
            gap = next_start - line["end"]
            if gap > 2.0:
                dot_clip = (
                    TextClip(
                        text="♪  ♪  ♪",
                        font_size=font_size - 10,
                        color="#888888",
                        font=font,
                        text_align="center",
                    )
                    .with_position(("center", height * 0.45))
                    .with_start(line["end"] + 0.5)
                    .with_duration(gap - 1.0)
                )
                lyric_clips.append(dot_clip)

    all_clips = [background, title_clip] + lyric_clips
    video = CompositeVideoClip(all_clips, size=resolution)
    video = video.with_audio(audio).with_duration(duration)

    print(f"Rendering video to '{output_path}'...")
    video.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        threads=4,
        preset="medium",
        logger="bar",
    )
    print(f"Done! Video saved to '{output_path}'")


def save_transcript(transcript: dict, output_path: str):
    """Save the transcript as JSON for reuse."""
    with open(output_path, "w") as f:
        json.dump(transcript, f, indent=2)
    print(f"Transcript saved to '{output_path}'")


def load_transcript(path: str) -> dict:
    """Load a previously saved transcript."""
    with open(path) as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(
        description="Generate a lyric video from a song using AI transcription"
    )
    parser.add_argument("audio", help="Path to the audio file (mp3, wav, etc.)")
    parser.add_argument("-o", "--output", default="lyric_video.mp4", help="Output video path")
    parser.add_argument(
        "-m", "--model", default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size (larger = more accurate but slower)",
    )
    parser.add_argument("--width", type=int, default=1920, help="Video width")
    parser.add_argument("--height", type=int, default=1080, help="Video height")
    parser.add_argument("--font-size", type=int, default=60, help="Lyric font size")
    parser.add_argument("--font", default="Arial-Bold", help="Font name")
    parser.add_argument("--bg-color", default="15,15,30", help="Background RGB, e.g. '15,15,30'")
    parser.add_argument("--text-color", default="white", help="Lyric text color")
    parser.add_argument("--highlight-color", default="#00BFFF", help="Karaoke highlight color")
    parser.add_argument("--words-per-line", type=int, default=8, help="Max words per lyric line")
    parser.add_argument(
        "--transcript", help="Path to a saved transcript JSON (skip transcription)"
    )
    parser.add_argument(
        "--save-transcript", help="Save transcript to this JSON path"
    )
    parser.add_argument(
        "--transcript-only", action="store_true",
        help="Only transcribe, don't generate video",
    )

    args = parser.parse_args()

    if not os.path.exists(args.audio):
        print(f"Error: Audio file '{args.audio}' not found.")
        sys.exit(1)

    if args.transcript:
        print(f"Loading transcript from '{args.transcript}'...")
        transcript = load_transcript(args.transcript)
    else:
        transcript = transcribe_song(args.audio, args.model)

    if args.save_transcript:
        save_transcript(transcript, args.save_transcript)

    if args.transcript_only:
        if not args.save_transcript:
            print(json.dumps(transcript, indent=2))
        return

    bg = tuple(int(c) for c in args.bg_color.split(","))

    create_lyric_video(
        audio_path=args.audio,
        transcript=transcript,
        output_path=args.output,
        resolution=(args.width, args.height),
        font_size=args.font_size,
        font=args.font,
        bg_color=bg,
        text_color=args.text_color,
        highlight_color=args.highlight_color,
        max_words_per_line=args.words_per_line,
    )


if __name__ == "__main__":
    main()
