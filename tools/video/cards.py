"""The title cards at the start and the end of every video, drawn frame by frame as SVG in the
colors of kleinod.studio and turned into video with rsvg-convert and ffmpeg.

    python3 tools/video/cards.py    # writes a still of each card to dist/videos/cards/

The intro sets the word "Typecase" letter by letter, like movable type dropping into a
composing stick; then the app icon and the kleinod.studio logo appear. The outro shows the same
lockup with a line under it, and "With love by" and the kleinod.studio logo once the narration
gets there. The intro has a sound of its own: a soft wooden tick as each letter lands, then a
two-note chime when the icon appears."""

import base64
import math
import random
import re
import subprocess
import wave
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

WIDTH, HEIGHT, FPS = 1920, 1080, 30
BACKGROUND = "#F7F6FC"
INK = "#2A2550"
MUTED = "#6A6590"
FONT = "Adwaita Sans"

INTRO = 3.6  # seconds

WORD = "Typecase"
WORD_SIZE = 168  # px
ICON_SIZE = 220


# --- Drawing ------------------------------------------------------------------------


@cache
def _inner(path: Path) -> tuple[str, str]:
    """The viewBox and the drawing inside an SVG file, to place it in a frame."""
    text = path.read_text()
    box = re.search(r'viewBox="([^"]+)"', text).group(1)
    body = re.sub(r"^.*?<svg[^>]*>|</svg>\s*$", "", text, flags=re.S)
    return box, body


def _place(path: Path, x: float, y: float, width: float, height: float, opacity: float = 1.0, scale: float = 1.0) -> str:
    box, body = _inner(path)
    cx, cy = x + width / 2, y + height / 2
    return (
        f'<g opacity="{opacity:.3f}" transform="translate({cx:.1f} {cy:.1f}) scale({scale:.4f}) translate({-cx:.1f} {-cy:.1f})">'
        f'<svg x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" viewBox="{box}">{body}</svg></g>'
    )


@cache
def _advances(text: str, size: int, weight: str = "Bold") -> list[float]:
    """Where each letter starts, measured with Pango, so the letters can move one by one."""
    import gi

    gi.require_version("Pango", "1.0")
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import Pango, PangoCairo

    layout = Pango.Layout(PangoCairo.FontMap.get_default().create_context())
    layout.set_font_description(Pango.FontDescription(f"{FONT} {weight} {size}px"))
    starts = []
    for index in range(len(text) + 1):
        layout.set_text(text[:index], -1)
        starts.append(layout.get_extents()[1].width / Pango.SCALE)
    return starts


def _clip(u: float) -> float:
    return max(0.0, min(1.0, u))


def _smooth(u: float) -> float:
    u = _clip(u)
    return u * u * (3 - 2 * u)


def _drop(u: float) -> float:
    """0 to 1 with a small settle at the end, like a piece of type landing."""
    u = _clip(u)
    back = 1.4
    return 1 + (back + 1) * (u - 1) ** 3 + back * (u - 1) ** 2


def _lockup(t_letters: list[float], icon: float, center_y: float) -> str:
    """The icon and the word next to it. t_letters: how far each letter has fallen (0..1);
    icon: how far the icon has appeared (0..1)."""
    starts = _advances(WORD, WORD_SIZE)
    word_width = starts[-1]
    gap = 44
    total = ICON_SIZE + gap + word_width
    left = (WIDTH - total) / 2
    parts = [_place(ROOT / "data" / "studio.kleinod.Typecase.svg", left, center_y - ICON_SIZE / 2, ICON_SIZE, ICON_SIZE,
                    opacity=_smooth(icon * 1.6), scale=0.82 + 0.18 * _drop(icon))]
    baseline = center_y + WORD_SIZE * 0.36
    x0 = left + ICON_SIZE + gap
    for letter, start, fallen in zip(WORD, starts, t_letters):
        if fallen <= 0:
            continue
        y = baseline - (1 - _drop(fallen)) * 140
        parts.append(
            f'<text x="{x0 + start:.1f}" y="{y:.1f}" font-family="{FONT}" font-weight="700" font-size="{WORD_SIZE}" '
            f'fill="{INK}" fill-opacity="{_smooth(fallen * 2.5):.3f}">{letter}</text>'
        )
    return "".join(parts)


def _frame(content: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">'
        f'<rect width="100%" height="100%" fill="{BACKGROUND}"/>{content}</svg>'
    )


def _studio(y: float, opacity: float, height: float = 64) -> str:
    """The kleinod.studio logo, centered."""
    width = height * 331 / 64
    return _place(HERE / "kleinod-studio-logo-horizontal.svg", (WIDTH - width) / 2, y, width, height, opacity=opacity)


def intro(t: float) -> str:
    letters = [(t - 0.25 - index * 0.085) / 0.45 for index in range(len(WORD))]
    icon = (t - 1.05) / 0.5
    studio = _smooth((t - 1.7) / 0.6)
    return _frame(_lockup(letters, icon, HEIGHT / 2 - 40) + _studio(HEIGHT - 190, studio, 56))


def outro(t: float, second: float) -> str:
    """second: when the narration reaches "With love by", in seconds of the card."""
    appear = _smooth(t / 0.6)
    lockup = _lockup([1.0] * len(WORD), 1.0, HEIGHT / 2 - 110)
    line = (
        f'<text x="{WIDTH / 2}" y="{HEIGHT / 2 + 90}" text-anchor="middle" font-family="{FONT}" font-size="54" '
        f'fill="{MUTED}" fill-opacity="{_smooth((t - 0.3) / 0.6):.3f}">Free software, made for GNOME</text>'
    )
    love = _smooth((t - second) / 0.6)
    credit = (
        f'<text x="{WIDTH / 2}" y="{HEIGHT - 205}" text-anchor="middle" font-family="{FONT}" font-size="34" '
        f'fill="{MUTED}" fill-opacity="{love:.3f}">With love by</text>'
    ) + _studio(HEIGHT - 180, love, 64)
    return _frame(f'<g opacity="{appear:.3f}">{lockup}{line}</g>{credit}')


def closing(t: float) -> str:
    """The end of a video without narration: the lockup, the line, the address of the website,
    and "With love by" a little later."""
    appear = _smooth(t / 0.6)
    lockup = _lockup([1.0] * len(WORD), 1.0, HEIGHT / 2 - 150)
    line = (
        f'<text x="{WIDTH / 2}" y="{HEIGHT / 2 + 50}" text-anchor="middle" font-family="{FONT}" font-size="54" '
        f'fill="{MUTED}" fill-opacity="{_smooth((t - 0.3) / 0.6):.3f}">Free software, made for GNOME</text>'
        f'<text x="{WIDTH / 2}" y="{HEIGHT / 2 + 130}" text-anchor="middle" font-family="{FONT}" font-weight="700" '
        f'font-size="46" fill="{VIOLET}" fill-opacity="{_smooth((t - 0.8) / 0.6):.3f}">kleinod.studio/typecase</text>'
    )
    love = _smooth((t - 1.8) / 0.6)
    credit = (
        f'<text x="{WIDTH / 2}" y="{HEIGHT - 175}" text-anchor="middle" font-family="{FONT}" font-size="34" '
        f'fill="{MUTED}" fill-opacity="{love:.3f}">With love by</text>'
    ) + _studio(HEIGHT - 150, love, 64)
    return _frame(f'<g opacity="{appear:.3f}">{lockup}{line}</g>{credit}')


def _still(svg: str, path: Path) -> Path:
    subprocess.run(["rsvg-convert", "-o", str(path)], input=svg.encode(), check=True)
    return path


def caption(text: str, path: Path) -> Path:
    """A word laid over the picture (a transparent 1920x1080 PNG): white card at the bottom left."""
    size = 64
    width = _advances(text, size)[-1] + 2 * 56 + 16
    x, y, height = 72, HEIGHT - 72 - 132, 132
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">'
        f'<defs><filter id="shadow" x="-20%" y="-40%" width="140%" height="180%"><feDropShadow dx="0" dy="10" '
        f'stdDeviation="18" flood-color="{INK}" flood-opacity="0.22"/></filter></defs>'
        f'<rect x="{x}" y="{y}" width="{width:.0f}" height="{height}" rx="26" fill="#fff" filter="url(#shadow)"/>'
        f'<rect x="{x + 40}" y="{y + 38}" width="8" height="{height - 76}" rx="4" fill="{VIOLET}"/>'
        f'<text x="{x + 72}" y="{y + height / 2 + size * 0.36:.0f}" font-family="{FONT}" font-weight="700" '
        f'font-size="{size}" fill="{INK}">{html_escape(text)}</text></svg>'
    )
    return _still(svg, path)


def pages(images: list[Path], path: Path, paper: tuple[float, float] = (148, 210)) -> Path:
    """Printed pages side by side on the background of the cards (a full 1920x1080 PNG)."""
    height = 880
    width = height * paper[0] / paper[1]
    gap = 90
    left = (WIDTH - len(images) * width - (len(images) - 1) * gap) / 2
    top = (HEIGHT - height) / 2
    shots = ""
    for number, image in enumerate(images):
        x = left + number * (width + gap)
        picture = base64.b64encode(image.read_bytes()).decode()
        shots += (
            f'<rect x="{x:.1f}" y="{top}" width="{width:.1f}" height="{height}" fill="#fff" filter="url(#shadow)"/>'
            f'<image x="{x:.1f}" y="{top}" width="{width:.1f}" height="{height}" preserveAspectRatio="xMidYMid slice" '
            f'href="data:image/png;base64,{picture}"/>'
        )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">'
        f'<defs><filter id="shadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="16" '
        f'stdDeviation="24" flood-color="{INK}" flood-opacity="0.2"/></filter></defs>'
        f'<rect width="100%" height="100%" fill="{BACKGROUND}"/>{shots}</svg>'
    )
    return _still(svg, path)


# --- Thumbnail -----------------------------------------------------------------------

VIOLET = "#4B3F9E"


def _wrap(text: str, size: int, width: float) -> list[str]:
    """Breaks text into lines no wider than width, at spaces."""
    lines = [""]
    for word in text.split():
        trial = f"{lines[-1]} {word}".strip()
        if lines[-1] and _advances(trial, size)[-1] > width:
            lines.append(word)
        else:
            lines[-1] = trial
    return lines


def thumbnail(title: str, topic: str, still: Path, path: Path) -> Path:
    """The picture that stands for a video before it plays (1280x720 JPEG): the topic and the
    title on the left, a still of the video on the right, running off the edge."""
    width, height = 1280, 720
    picture = base64.b64encode(still.read_bytes()).decode()
    shot_x, shot_y, shot_w = 640, 150, 820
    shot_h = shot_w * 9 / 16
    size = 72
    lines = _wrap(title, size, 500)
    top = 330 - (len(lines) - 1) * size * 0.55
    title_svg = "".join(
        f'<text x="72" y="{top + 30 + number * size * 1.12:.1f}" font-family="{FONT}" font-weight="700" '
        f'font-size="{size}" fill="{INK}">{html_escape(line)}</text>'
        for number, line in enumerate(lines)
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<defs><clipPath id="shot"><rect x="{shot_x}" y="{shot_y}" width="{shot_w}" height="{shot_h:.1f}" rx="18"/></clipPath>'
        f'<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="14" stdDeviation="22" '
        f'flood-color="{INK}" flood-opacity="0.18"/></filter></defs>'
        f'<rect width="100%" height="100%" fill="{BACKGROUND}"/>'
        f'<rect x="{shot_x}" y="{shot_y}" width="{shot_w}" height="{shot_h:.1f}" rx="18" fill="#fff" filter="url(#shadow)"/>'
        f'<image x="{shot_x}" y="{shot_y}" width="{shot_w}" height="{shot_h:.1f}" clip-path="url(#shot)" '
        f'preserveAspectRatio="xMidYMid slice" href="data:image/png;base64,{picture}"/>'
        f'<rect x="{shot_x}" y="{shot_y}" width="{shot_w}" height="{shot_h:.1f}" rx="18" fill="none" stroke="#DEDBF0" stroke-width="2"/>'
        + _place(ROOT / "data" / "studio.kleinod.Typecase.svg", 66, 62, 72, 72)
        + f'<text x="150" y="112" font-family="{FONT}" font-weight="700" font-size="40" fill="{INK}">Typecase</text>'
        f'<text x="74" y="{top - 58:.1f}" font-family="{FONT}" font-weight="700" font-size="26" letter-spacing="3" '
        f'fill="{VIOLET}">{html_escape(topic.upper())}</text>'
        + title_svg
        + _place(HERE / "kleinod-studio-logo-horizontal.svg", 74, height - 96, 36 * 331 / 64, 36)
        + "</svg>"
    )
    png = subprocess.run(["rsvg-convert", "-f", "png"], input=svg.encode(), capture_output=True, check=True).stdout
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "png_pipe", "-i", "-", "-q:v", "2", str(path)], input=png, check=True)
    return path


def html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# --- Sound ---------------------------------------------------------------------------

RATE = 48000


def _landed(index: int) -> float:
    """When letter `index` of the intro first reaches its line (_drop passes 1 at u = 0.417)."""
    return 0.25 + index * 0.085 + 0.417 * 0.45


def _tick(out: list[float], at: float, pitch: float, level: float, noise: random.Random) -> None:
    """A short wooden tick, like a piece of type set down: a bar tone with its overtone and a
    click of noise."""
    start = round(at * RATE)
    smooth = 0.0
    for n in range(round(0.12 * RATE)):
        t = n / RATE
        tone = math.sin(2 * math.pi * pitch * t) * math.exp(-t / 0.028)
        tone += 0.35 * math.sin(2 * math.pi * pitch * 3.93 * t) * math.exp(-t / 0.008)
        smooth += 0.35 * (noise.uniform(-1, 1) - smooth)
        tone += 0.6 * smooth * math.exp(-t / 0.003)
        out[start + n] += level * tone


def _bell(out: list[float], at: float, pitch: float, level: float, length: float) -> None:
    """A soft bell: a few partials that die away at different speeds, with a gentle start."""
    start = round(at * RATE)
    partials = [(1.0, 1.0, 0.9), (2.0, 0.35, 0.55), (2.76, 0.18, 0.35), (5.4, 0.06, 0.15)]
    for n in range(min(round(length * RATE), len(out) - start)):
        t = n / RATE
        attack = min(1.0, t / 0.006)
        value = sum(gain * math.sin(2 * math.pi * pitch * ratio * t) * math.exp(-t / decay)
                    for ratio, gain, decay in partials)
        out[start + n] += level * attack * value


def signature(path: Path) -> Path:
    """Writes the sound of the intro as a WAV file of INTRO seconds."""
    out = [0.0] * round(INTRO * RATE)
    noise = random.Random(7)  # the same sound every time
    for index in range(len(WORD)):
        _tick(out, _landed(index), 1180 + 40 * index + noise.uniform(-25, 25), 0.10, noise)
    icon = 1.05 + 0.417 * 0.5
    _bell(out, icon, 659.25, 0.16, INTRO - icon)  # E5
    _bell(out, icon + 0.11, 987.77, 0.12, INTRO - icon - 0.11)  # B5
    # a little room: two quiet echoes
    for delay, gain in [(0.067, 0.22), (0.149, 0.12)]:
        shift = round(delay * RATE)
        for n in range(len(out) - 1, shift - 1, -1):
            out[n] += gain * out[n - shift]
    fade = round(0.4 * RATE)
    for n in range(fade):
        out[-1 - n] *= n / fade
    peak = max(abs(v) for v in out)
    with wave.open(str(path), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(RATE)
        file.writeframes(b"".join(int(v / peak * 0.32 * 32767).to_bytes(2, "little", signed=True) for v in out))
    return path


# --- Turning frames into video ------------------------------------------------------


def render(draw, length: float, path: Path) -> Path:
    """Writes the card as a lossless video of `length` seconds; draw(t) returns one frame as SVG."""
    encoder = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "png", "-i", "-",
         "-c:v", "libx264", "-crf", "12", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(path)],
        stdin=subprocess.PIPE,
    )
    for number in range(round(length * FPS)):
        png = subprocess.run(["rsvg-convert", "-f", "png"], input=draw(number / FPS).encode(), capture_output=True, check=True)
        encoder.stdin.write(png.stdout)
    encoder.stdin.close()
    if encoder.wait():
        raise RuntimeError("ffmpeg could not write the card")
    return path


if __name__ == "__main__":
    folder = ROOT / "dist" / "videos" / "cards"
    folder.mkdir(parents=True, exist_ok=True)
    for name, svg in [("intro-1.0", intro(1.0)), ("intro-end", intro(INTRO)), ("outro-end", outro(6.0, 3.0)),
                      ("closing-end", closing(5.0))]:
        subprocess.run(["rsvg-convert", "-o", str(folder / f"{name}.png")], input=svg.encode(), check=True)
        print(folder / f"{name}.png")
    print(caption("Organize.", folder / "caption.png"))
    print(signature(folder / "signature.wav"))
