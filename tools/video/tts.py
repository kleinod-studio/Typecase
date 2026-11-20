"""Speaks the narration of a video. Runs inside the Python environment of the speech synthesizer
(see videokit.VOICES), not inside the app:

    <venv>/bin/python -I tts.py <engine> <voice> <language> <output folder> [tools] < lines.json

lines.json is a list of sentences; the result is say-00.wav, say-01.wav ... in the folder.
Engine: "kokoro" (Kokoro, Apache-2.0). Voices starting with "a" speak American English, with
"b" British English."""

import json
import sys
import wave
from pathlib import Path

import numpy as np


def write(path: Path, samples, rate: int) -> None:
    samples = np.asarray(samples, dtype=np.float32).reshape(-1)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())


def kokoro(voice: str, language: str, tools: Path):
    from kokoro_onnx import Kokoro

    model = Kokoro(str(tools / "kokoro" / "kokoro-v1.0.onnx"), str(tools / "kokoro" / "voices-v1.0.bin"))
    lang = {"a": "en-us", "b": "en-gb"}[voice[0]]

    def say(text):
        return model.create(text, voice=voice, speed=1.0, lang=lang)

    return say


def main():
    engine, voice, language, folder = sys.argv[1:5]
    tools = Path(__file__).resolve().parent if len(sys.argv) < 6 else Path(sys.argv[5])
    say = {"kokoro": kokoro}[engine](voice, language, tools)
    for number, text in enumerate(json.load(sys.stdin)):
        samples, rate = say(text)
        write(Path(folder) / f"say-{number:02}.wav", samples, rate)


if __name__ == "__main__":
    main()
