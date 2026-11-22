"""Records short explainer videos of Typecase: the real app plays a scripted scene by itself,
the screen is recorded, and a narration with subtitles is added.

A video is a list of scenes. Each scene has a sentence in English and in German and the steps it
shows in the app. The app, its sample library (demo_library.py) and the narration are in English;
the subtitles come in English and German. Because everything comes from the script, a video can
simply be made again when the app changes.

Needs Hyprland (to place the window), wf-recorder, ffmpeg, rsvg-convert, and the speech
synthesizer Kokoro (Apache-2.0) in ~/.cache/typecase-video/; it runs on this computer, nothing
goes online:
    python3 -m venv venv && venv/bin/pip install kokoro-onnx
    kokoro/kokoro-v1.0.onnx and kokoro/voices-v1.0.bin from
        github.com/thewh1teagle/kokoro-onnx/releases (model-files-v1.0)
Spoken sentences are kept in ~/.cache/typecase-video/speech/, so a new take only speaks what changed.

The intro plays the sound logo ~/.cache/typecase-video/sound-logo.mp3 ("Sound Soul – This Logo
Reveal" by Diamond_Tunes from Pixabay; its license allows using it in videos, not passing the file
on, so it stays out of the repository). Without it the intro has the sound cards.py makes.

The app runs with its own temporary library and configuration; your data is never touched."""

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TOOLS = Path(os.environ.get("TYPECASE_VIDEO_TOOLS", Path.home() / ".cache" / "typecase-video"))
OUTPUT = ROOT / "dist" / "videos"

# language: (Python of the synthesizer, engine, voice); German videos have subtitles only
VOICES = {
    "en": (TOOLS / "venv" / "bin" / "python", "kokoro", "af_heart"),
}

WIDTH, HEIGHT = 1280, 720  # window size in logical pixels; the video is 1920x1080
GAP = 0.6  # seconds of quiet after each sentence
SPEECH = 7  # raise when tts.py speaks differently, so the cached sentences are made again
MAX_ZOOM = 1.5  # the recording has twice the pixels, so this stays sharp enough
SOUND_LOGO = TOOLS / "sound-logo.mp3"
SOUND_LOGO_CREDIT = {"title": "Sound Soul – This Logo Reveal", "artist": "Diamond_Tunes",
                     "artist_url": "https://pixabay.com/users/diamond_tunes-25553362/",
                     "source": "Pixabay", "source_url": "https://pixabay.com/"}
SOUND_LOGO_VOLUME = 0.4  # the file is loud

LANGUAGE = "en"  # of the run in progress


@dataclass
class Scene:
    en: str  # English narration
    de: str  # German narration
    steps: object = None  # generator function(app_window) that yields seconds to wait
    hold: float = 0.0  # extra seconds at the end of the scene
    say: str = ""  # how the voice is to say it, if not as written (names, for example)
    length: float = 0.0  # music videos: the scene lasts exactly this long (seconds, to the beat)
    overlays: list = field(default_factory=list)  # music videos: (caption text or PNG path, from, to), seconds into the scene
    start: float = field(default=0.0, init=False)  # when it began, in seconds of video
    duration: float = field(default=0.0, init=False)  # length of the narration

    def text(self, language: str) -> str:
        return self.en if language == "en" else self.de

    def spoken(self, language: str) -> str:
        return self.say or self.text(language)


# The end of every video, spoken over the closing card (cards.py)
OUTRO = [
    Scene("Typecase. Free software, made for GNOME.", "Typecase. Freie Software, gemacht für GNOME.", say="Type case. Free software, made for GNOME."),
    Scene("With love, by kleinod.studio.", "Mit Liebe gemacht von kleinod.studio.", say="With love, by Kline oat dot studio."),
]
FADE = 0.5  # seconds the cards cross-fade into the recording and back


# --- Narration -------------------------------------------------------------


def speak(scenes: list[Scene], language: str, folder: Path) -> list[Path]:
    """One WAV file per scene; sentences spoken before are taken from the cache."""
    python, engine, voice = VOICES[language]
    if not python.exists():
        sys.exit(f"The speech synthesizer for {language} is missing; see the notes at the top of {Path(__file__).name}.")
    cache = TOOLS / "speech"
    cache.mkdir(parents=True, exist_ok=True)

    def cached(text):
        key = hashlib.sha256(f"{SPEECH}\n{engine}\n{voice}\n{language}\n{text}".encode()).hexdigest()[:24]
        return cache / f"{key}.wav"

    missing = list(dict.fromkeys(scene.spoken(language) for scene in scenes if not cached(scene.spoken(language)).exists()))
    if missing:
        with tempfile.TemporaryDirectory(dir=TOOLS) as spoken:
            subprocess.run(
                [str(python), "-I", str(HERE / "tts.py"), engine, voice, language, spoken, str(TOOLS)],
                input=json.dumps(missing), text=True, check=True,
            )
            for number, text in enumerate(missing):
                shutil.move(Path(spoken) / f"say-{number:02}.wav", cached(text))
    files = []
    for number, scene in enumerate(scenes):
        path = folder / f"say-{number:02}.wav"
        shutil.copyfile(cached(scene.spoken(language)), path)
        with wave.open(str(path)) as audio:
            scene.duration = audio.getnframes() / audio.getframerate()
        files.append(path)
    return files


# --- Subtitles -------------------------------------------------------------


def _stamp(seconds: float) -> str:
    hours, rest = divmod(max(0.0, seconds), 3600)
    minutes, rest = divmod(rest, 60)
    return f"{int(hours):02}:{int(minutes):02}:{rest:06.3f}"


def write_subtitles(scenes: list[Scene], path: Path, language: str) -> None:
    """WebVTT subtitles, one cue per scene, shown while it is spoken."""
    lines = ["WEBVTT", ""]
    for scene in scenes:
        lines += [f"{_stamp(scene.start)} --> {_stamp(scene.start + scene.duration + 0.3)}", scene.text(language), ""]
    path.write_text("\n".join(lines), encoding="utf-8")


# --- Demo library and configuration ------------------------------------------


def prepare_home(language: str, settings: dict | None = None, extras: bool = False) -> Path:
    """A temporary home for the app: XDG folders, a configuration and the sample library.
    settings are added to the configuration; extras adds the tour's sheets to the library.
    Returns the temporary folder (deleted by the caller)."""
    import demo_library

    temp = Path(tempfile.mkdtemp(prefix="typecase-video-", dir=Path.home() / ".cache"))
    library = demo_library.build(temp / demo_library.TEXT[language]["library"], language, extras=extras)
    os.environ["XDG_CONFIG_HOME"] = str(temp / "cfg")
    os.environ["XDG_DATA_HOME"] = str(temp / "data")
    os.environ["LANGUAGE"] = language
    (temp / "cfg" / "typecase").mkdir(parents=True)
    config = {"library_path": str(library), "color_scheme": "light", "spell_check": False, **(settings or {})}
    (temp / "cfg" / "typecase" / "config.json").write_text(json.dumps(config), encoding="utf-8")
    return temp


def name(english: str) -> str:
    """The name of a library row in the language of this run."""
    import demo_library

    return demo_library.NAMES[LANGUAGE].get(english, english)


# --- Window and recording ----------------------------------------------------


def _hyprctl(*args: str) -> str:
    return subprocess.run(["hyprctl", *args], text=True, capture_output=True, check=False).stdout


def place_window() -> tuple[int, int, int, int] | None:
    """Floats this process's window at the recording size in the middle of the screen.
    Returns its position and size (logical pixels), or None if Hyprland does not know it."""

    def ours():
        for client in json.loads(_hyprctl("-j", "clients") or "[]"):
            if client.get("pid") == os.getpid():
                return client
        return None

    client = ours()
    if client is None:
        return None
    if client["size"] != [WIDTH, HEIGHT] or not client["floating"]:
        target = f'window = "address:{client["address"]}"'
        lua = (  # Hyprland 0.55 and later take Lua
            f"hl.dsp.window.float({{ action = \"on\", {target} }})",
            f"hl.dsp.window.resize({{ x = {WIDTH}, y = {HEIGHT}, {target} }})",
            f"hl.dsp.window.center({{ {target} }})",
        )
        if "error" in _hyprctl("dispatch", lua[0]):
            address = f"address:{client['address']}"
            _hyprctl("dispatch", "setfloating", address)
            _hyprctl("dispatch", "resizewindowpixel", f"exact {WIDTH} {HEIGHT},{address}")
            _hyprctl("dispatch", "centerwindow")
        else:
            for command in lua[1:]:
                _hyprctl("dispatch", command)
            # square, borderless and opaque, so only the app is in the picture
            for prop, value in (("rounding", "0"), ("border_size", "0"), ("opaque", "1"), ("no_shadow", "1")):
                _hyprctl("dispatch", f'hl.dsp.window.set_prop({{ prop = "{prop}", value = "{value}", {target} }})')
        client = ours()
    (x, y), (w, h) = client["at"], client["size"]
    return x, y, w, h


class Recorder:
    """Records a part of the screen with wf-recorder."""

    def __init__(self, geometry: tuple[int, int, int, int], path: Path):
        x, y, w, h = geometry
        self.path = path
        self.started = time.monotonic()
        self.process = subprocess.Popen(
            ["wf-recorder", "-y", "-g", f"{x},{y} {w}x{h}", "-r", "30", "-c", "libx264",
             "-p", "crf=14", "-p", "preset=veryfast", "-f", str(path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def now(self) -> float:
        return time.monotonic() - self.started

    def stop(self) -> float:
        """Stops recording and returns how much later than started the video really began."""
        wall = self.now()
        self.process.send_signal(signal.SIGINT)
        self.process.wait(timeout=30)
        duration = float(
            subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(self.path)],
                text=True, capture_output=True, check=True,
            ).stdout
        )
        return max(0.0, wall - duration)


# --- Zooming -----------------------------------------------------------------

_state = {"recorder": None, "window": None, "scene_start": 0.0}


def at(seconds: float) -> float:
    """For steps of a music video: how long to wait until `seconds` after the scene began, so a
    step can `yield at(2.4)` to land on the beat however long the steps before it took."""
    recorder = _state["recorder"]
    return max(0.0, _state["scene_start"] + seconds - recorder.now()) if recorder else 0.0
_zooms: list[tuple[float, float, tuple[float, float, float]]] = []  # start, length, (zoom, center x, center y)


def zoom_to(widget=None, length: float = 1.2, margin: float = 0.12, factor: float | None = None) -> float:
    """Glides the picture towards a widget (or back to the whole window, without one).
    Returns the length, so a step can `yield zoom_to(...)` to wait for it."""
    win, recorder = _state["window"], _state["recorder"]
    if recorder is None:
        return 0.0
    if widget is None:
        target = (1.0, 0.5, 0.5)
    else:
        if isinstance(widget, tuple):  # a rectangle in the window: x, y, width, height
            left, top, width, height = widget
        else:
            found, bounds = widget.compute_bounds(win)
            if not found:
                return 0.0
            left, top, width, height = bounds.get_x(), bounds.get_y(), bounds.get_width(), bounds.get_height()
        w, h = width / WIDTH, height / HEIGHT
        x, y = left / WIDTH + w / 2, top / HEIGHT + h / 2
        z = factor or min(MAX_ZOOM, 1 / max(w + 2 * margin, h + 2 * margin, 1 / MAX_ZOOM))
        target = (max(1.0, z), x, y)
    _zooms.append((recorder.now(), length, target))
    print(f"zoom {target[0]:.2f} at {target[1]:.2f}, {target[2]:.2f}", file=sys.stderr)
    return length


def _zoom_filter() -> str:
    """scale and crop with expressions over time: every zoom eases from the last view to its own."""
    if not _zooms:
        return "scale=1920:1080:flags=lanczos"
    views = [(0.0, 0.0, (1.0, 0.5, 0.5))] + sorted(_zooms)

    t = "(in/30)"  # perspective knows no time, only the frame number (the input runs at 30 fps)

    def expression(index):
        # Built from the last zoom backwards: before a zoom starts, its eased value is still the
        # view before it, so each step only has to say when it is over.
        expr = f"{views[-1][2][index]:.4f}"
        for (start, length, view), (_s, _l, before) in reversed(list(zip(views[1:], views[:-1]))):
            a, b = before[index], view[index]
            u = f"clip(({t}-{start:.3f})/{max(length, 0.01):.3f},0,1)"
            eased = f"({a:.4f}+({b - a:.4f})*{u}*{u}*(3-2*{u}))"
            expr = f"if(lt({t},{start + length:.3f}),{eased},{expr})"
        return expr

    z, cx, cy = expression(0), expression(1), expression(2)
    # perspective sends the corners of the shown part to the corners of the frame. Unlike scale
    # and crop it works between pixels, so a slow glide moves smoothly instead of in pixel steps.
    left = f"clip(({cx}-0.5/{z})*W,0,W-W/{z})"
    top = f"clip(({cy}-0.5/{z})*H,0,H-H/{z})"
    right, bottom = f"{left}+W/{z}", f"{top}+H/{z}"
    corners = [left, top, right, top, left, bottom, right, bottom]
    points = ":".join(f"{name}='{value}'" for name, value in zip(["x0", "y0", "x1", "y1", "x2", "y2", "x3", "y3"], corners))
    return f"perspective={points}:interpolation=cubic:eval=frame,scale=1920:1080:flags=lanczos"


# --- Putting the video together ----------------------------------------------


def assemble(scenes: list[Scene], voices: list[Path], screen: Path, work: Path, folder: Path, name: str) -> list[Path]:
    """Puts the intro card with its signature sound, the screen recording with its zooms and the closing card together,
    adds the narration (one file per scene, then the two of OUTRO) and writes WebM and MP4
    versions at 1920x1080, with English and German subtitles next to them. Scene times are
    seconds of the recording; here they become seconds of the video."""
    import cards

    folder.mkdir(parents=True, exist_ok=True)
    length = scenes[-1].start + scenes[-1].duration + GAP + scenes[-1].hold  # of the recording
    lead = cards.INTRO - FADE  # where the recording begins in the video
    closing = lead + length - FADE  # where the closing card begins
    for scene in scenes:
        scene.start += lead
    moment = closing + 0.6
    for scene in OUTRO:
        scene.start = moment
        moment += scene.duration + GAP
    outro_length = moment - closing + 1.0
    total = closing + outro_length
    intro = cards.render(cards.intro, cards.INTRO, work / "intro.mp4")
    outro = cards.render(lambda t: cards.outro(t, OUTRO[1].start - closing), outro_length, work / "outro.mp4")

    every = scenes + OUTRO
    sound = intro_sound(work)
    inputs = ["-i", str(intro), "-i", str(screen), "-i", str(outro), "-i", str(sound)]
    filters = ["[3:a]aresample=48000[a3]"]
    for number, (scene, voice) in enumerate(zip(every, voices), start=4):
        inputs += ["-i", str(voice)]
        filters.append(f"[{number}:a]aresample=48000,adelay={int(scene.start * 1000)}:all=1[a{number}]")
    mixed = "".join(f"[a{n}]" for n in range(3, 4 + len(every)))
    filters.append(f"{mixed}amix=inputs={len(every) + 1}:normalize=0,apad=whole_dur={total:.3f},aformat=channel_layouts=stereo[audio]")
    same = "fps=30,format=yuv420p,setsar=1,settb=AVTB"
    filters += [
        f"[0:v]{same}[intro]",
        f"[1:v]fps=30,{_zoom_filter()},trim=0:{length:.3f},setpts=PTS-STARTPTS,{same}[screen]",
        f"[2:v]{same}[outro]",
        f"[intro][screen]xfade=transition=fade:duration={FADE}:offset={lead:.3f}[opened]",
        f"[opened][outro]xfade=transition=fade:duration={FADE}:offset={closing:.3f},fade=t=out:st={total - 0.6:.2f}:d=0.6[video]",
    ]
    outputs = _encode(inputs, filters, total, folder, name)
    for language in ("en", "de"):
        path = folder / f"{name}.{language}.vtt"
        write_subtitles(every, path, language)
        outputs.append(path)
    return outputs


def intro_sound(work: Path) -> Path:
    """The sound of the intro: the sound logo, starting when the first letter lands, or else the
    sound cards.py makes."""
    import cards

    if not SOUND_LOGO.exists():
        return cards.signature(work / "signature.wav")
    path = work / "sound-logo.wav"
    delay = int(cards._landed(0) * 1000)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(SOUND_LOGO), "-af",
                    f"aresample=48000,adelay={delay}:all=1,volume={SOUND_LOGO_VOLUME}", str(path)], check=True)
    return path


def _encode(inputs: list[str], filters: list[str], total: float, folder: Path, name: str) -> list[Path]:
    """Writes the [video] and [audio] of the filter graph as WebM and MP4."""
    graph = ";".join(filters)
    outputs = []
    for extension, codecs in [
        ("webm", ["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0", "-row-mt", "1", "-c:a", "libopus", "-b:a", "128k"]),
        ("mp4", ["-c:v", "libx264", "-crf", "20", "-preset", "slow", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]),
    ]:
        path = folder / f"{name}.{extension}"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", graph, "-map", "[video]", "-map", "[audio]",
             "-t", f"{total:.2f}", *codecs, str(path)],
            check=True,
        )
        outputs.append(path)
    return outputs


def _duration(path: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                                text=True, capture_output=True, check=True).stdout)


def assemble_music(scenes: list[Scene], music: Path, work: Path, folder: Path, name: str, intro_length: float,
                   signature_volume: float | None = None) -> list[Path]:
    """Music videos: the intro card, the recording from the first scene on with its zooms and
    overlays, and the closing card until the music ends; the signature sound plays over the music."""
    import cards

    folder.mkdir(parents=True, exist_ok=True)
    first = scenes[0].start  # of the recording
    length = sum(scene.length for scene in scenes)
    lead = intro_length - FADE
    closing = lead + length - FADE
    total = _duration(music)
    intro = cards.render(cards.intro, intro_length, work / "intro.mp4")
    outro = cards.render(cards.closing, total - closing, work / "closing.mp4")
    sound = intro_sound(work)
    if signature_volume is None:  # the sound logo already has its volume; the made-up sound is quieter under music
        signature_volume = 1.0 if SOUND_LOGO.exists() else 0.6
    inputs = ["-i", str(intro), "-i", str(work / "screen.mkv"), "-i", str(outro), "-i", str(music), "-i", str(sound)]
    same = "fps=30,format=yuv420p,setsar=1,settb=AVTB"
    stereo = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
    filters = [
        f"[3:a]{stereo},afade=t=out:st={total - 1.5:.2f}:d=1.5[music]",
        f"[4:a]{stereo},volume={signature_volume}[sig]",
        "[music][sig]amix=inputs=2:normalize=0:duration=first[audio]",
        f"[0:v]{same}[intro]",
        f"[1:v]fps=30,{_zoom_filter()},trim=start={first:.3f}:end={first + length:.3f},setpts=PTS-STARTPTS,{same}[screen]",
        f"[2:v]{same}[outro]",
        f"[intro][screen]xfade=transition=fade:duration={FADE}:offset={lead:.3f}[opened]",
        f"[opened][outro]xfade=transition=fade:duration={FADE}:offset={closing:.3f}[v0]",
    ]
    last, number = "v0", 5
    for index, scene in enumerate(scenes):
        for kind, begin, end in scene.overlays:
            picture = Path(kind) if isinstance(kind, Path) else cards.caption(kind, work / f"caption-{index}-{number}.png")
            at_video, span = lead + (scene.start - first) + begin, end - begin
            fade = min(0.35, span / 3)
            inputs += ["-loop", "1", "-framerate", "30", "-t", f"{span:.3f}", "-i", str(picture)]
            filters += [
                f"[{number}:v]format=rgba,fade=t=in:st=0:d={fade:.2f}:alpha=1,fade=t=out:st={span - fade:.3f}:d={fade:.2f}:alpha=1,"
                f"setpts=PTS-STARTPTS+{at_video:.3f}/TB[o{number}]",
                f"[{last}][o{number}]overlay=eof_action=pass:format=auto[v{number}]",
            ]
            last, number = f"v{number}", number + 1
    filters.append(f"[{last}]fade=t=out:st={total - 1.0:.2f}:d=1.0,format=yuv420p[video]")
    return _encode(inputs, filters, total, folder, name)


# --- Running the scenes in the app --------------------------------------------


@dataclass
class Video:
    """What the website and the thumbnail say about a video."""

    name: str  # file name, also the anchor on the website
    title: str  # short, it goes on the thumbnail in big letters
    topic: str  # the section of the website's video page, e.g. "Organize your texts"
    summary: str  # one sentence under the title on the website
    still: float  # second of the finished video shown on the thumbnail
    music: dict | None = None  # credit under the video: title, artist, artist_url, source, source_url
    commands: list[tuple[str, str]] | None = None  # shown under the video, ready to copy: (what it does, command)


def run(video: Video, scenes: list[Scene], before=None) -> None:
    """Speaks the narration, plays the scenes in the real app while recording, then puts the
    video together in dist/videos/<name>/<name>.*, with a thumbnail (.jpg) and its details for
    the website (.json). before(window) prepares the first picture.

    TYPECASE_VIDEO_KEEP=1 keeps the work folder; TYPECASE_VIDEO_REUSE=<that folder> puts the video
    together again from its recording without recording anew (to try out cards or narration)."""
    work, reused = _work(video)
    voices = speak(scenes + OUTRO, LANGUAGE, work)
    if reused:
        _restore(scenes, work)
    else:
        _record(scenes, work, before, prepare_home(LANGUAGE))
    folder = OUTPUT / video.name
    finish(video, work, assemble(scenes, voices, work / "screen.mkv", work, folder, video.name))


def run_music(video: Video, scenes: list[Scene], music: Path, before=None, settings: dict | None = None,
              extras: bool = False, intro: float = 0.0) -> None:
    """A video without narration, cut to a piece of music: every scene lasts exactly its
    `length`, and its steps wait for the beat with at(). The intro card lasts `intro` seconds
    (cross-fading into the first scene), the closing card fills the rest of the music. Captions and
    pictures from the scenes' `overlays` are laid over the recording. settings and extras are
    passed to prepare_home. TYPECASE_VIDEO_KEEP and TYPECASE_VIDEO_REUSE work as in run()."""
    import cards

    work, reused = _work(video)
    if reused:
        _restore(scenes, work)
    else:
        _record(scenes, work, before, prepare_home(LANGUAGE, settings, extras), timed=True)
    folder = OUTPUT / video.name
    finish(video, work, assemble_music(scenes, music, work, folder, video.name, intro or cards.INTRO))


def _work(video: Video) -> tuple[Path, bool]:
    """The work folder of a take and whether it is an earlier one being put together again."""
    reuse = os.environ.get("TYPECASE_VIDEO_REUSE")
    if not reuse:
        return Path(tempfile.mkdtemp(prefix=f"typecase-video-{video.name}-", dir=Path.home() / ".cache")), False
    return Path(reuse), True


def _restore(scenes: list[Scene], work: Path) -> None:
    take = json.loads((work / "take.json").read_text())
    for scene, start in zip(scenes, take["starts"]):
        scene.start = start
    _zooms[:] = [tuple(zoom) for zoom in take["zooms"]]


def _record(scenes: list[Scene], work: Path, before, temp: Path, timed: bool = False) -> None:
    """Plays the scenes in the real app and records the window to work/screen.mkv. Sets each
    scene's start (seconds of the recording) and keeps the zooms; both go to work/take.json.
    timed: every scene ends exactly `length` seconds after it began (music videos)."""
    sys.path.insert(0, str(ROOT / "src"))

    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Gio, GLib

    from typecase.main import TypecaseApplication
    from typecase.window import TypecaseWindow

    failed = []

    def play(win):
        geometry = None
        for _ in range(20):
            yield 0.25
            geometry = place_window()
            if geometry and geometry[2:] == (WIDTH, HEIGHT):
                break
        if not geometry or geometry[2:] != (WIDTH, HEIGHT):
            failed.append(f"Hyprland did not place the window ({geometry}).")
            return
        if before:
            before(win)
        yield 1.5  # time for the layout to settle
        _state["window"] = win
        _state["recorder"] = recorder = Recorder(geometry, work / "screen.mkv")
        yield 1.0
        planned = recorder.now()
        for scene in scenes:
            scene.start = planned if timed else recorder.now()
            _state["scene_start"] = scene.start
            began = time.monotonic()
            if scene.steps:
                yield from scene.steps(win)
            if timed:
                planned += scene.length
                late = recorder.now() - planned
                if late > 0.05:
                    print(f"scene at {scene.start:.2f}s ran {late:.2f}s too long", file=sys.stderr)
                yield max(0.0, planned - recorder.now())
            else:
                left = scene.duration + GAP - (time.monotonic() - began)
                yield max(0.0, left) + scene.hold
        offset = recorder.stop()
        for scene in scenes:
            scene.start -= offset
        _zooms[:] = [(start - offset, length, view) for start, length, view in _zooms]

    def on_activate(app):
        win = TypecaseWindow(application=app)
        win.present()
        steps = play(win)

        def advance():
            try:
                delay = next(steps)
            except StopIteration:
                app.quit()
                return GLib.SOURCE_REMOVE
            except Exception as error:  # end the run instead of leaving it hanging
                import traceback

                traceback.print_exc()
                failed.append(repr(error))
                if _state["recorder"]:
                    _state["recorder"].process.send_signal(signal.SIGINT)
                app.quit()
                return GLib.SOURCE_REMOVE
            GLib.timeout_add(max(1, int(delay * 1000)), advance)
            return GLib.SOURCE_REMOVE

        GLib.timeout_add(500, advance)

    app = TypecaseApplication()
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    app.connect("activate", on_activate)
    app.run(None)
    shutil.rmtree(temp, ignore_errors=True)
    if failed:
        sys.exit(f"Recording failed: {failed[0]}")
    (work / "take.json").write_text(json.dumps({"starts": [scene.start for scene in scenes], "zooms": _zooms}))


def finish(video: Video, work: Path, outputs: list[Path]) -> None:
    """Adds the thumbnail and the details for the website to the finished video."""
    import cards

    name, folder = video.name, OUTPUT / video.name
    still = work / "still.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(video.still), "-i", str(folder / f"{name}.mp4"),
                    "-frames:v", "1", str(still)], check=True)
    outputs.append(cards.thumbnail(video.title, video.topic, still, folder / f"{name}.jpg"))
    details = {"title": video.title, "topic": video.topic, "summary": video.summary}
    if video.music:
        details["music"] = video.music
    if video.commands:
        details["commands"] = [{"note": note, "command": command} for note, command in video.commands]
    if SOUND_LOGO.exists():
        details["sound_logo"] = SOUND_LOGO_CREDIT
    (folder / f"{name}.json").write_text(json.dumps(details, indent=2, ensure_ascii=False) + "\n")
    outputs.append(folder / f"{name}.json")
    if os.environ.get("TYPECASE_VIDEO_KEEP") or os.environ.get("TYPECASE_VIDEO_REUSE"):
        print(work)
    else:
        shutil.rmtree(work, ignore_errors=True)
    for path in outputs:
        print(path)
