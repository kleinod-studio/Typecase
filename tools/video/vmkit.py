"""Records explainer videos on a whole desktop instead of the Typecase window: a virtual machine
with Ubuntu (or another GNOME system), reached over SSH, plays a scripted scene by itself. The
narration, cards, zooms and subtitles are the same as in videokit.py.

The VM runs vm_remote.py, which holds a remote desktop session of GNOME's own (Mutter), records
the screen and types, clicks and reads the terminal on command. Setting up the VM once:

    - SSH with a key, reachable as `typecase-vm` (Host entry in ~/.ssh/config; TYPECASE_VM changes the name)
    - the display at 3840x2160 with 200 % scaling: python3 vm/display.py 3840x2160@60.000 2 (in the VM's session)
    - the extension vm/hide-recording-indicator@kleinod.studio in ~/.local/share/gnome-shell/extensions/,
      enabled, so the recording icon stays out of the top bar; then log out and in again
    - English as the language of the account; the desktop in its factory look
    - a neutral prompt: the file ~/typecase-video/neutral-prompt switches ~/.bashrc to "you@ubuntu"

Steps of a scene are generator functions that get the VM and yield seconds to wait, like the
steps in videokit. Waiting for something the viewer need not watch (a password typed by hand,
a long download) can be cut out of the video: vm.cut() ... vm.uncut()."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import videokit
from videokit import GAP, OUTPUT, Scene, Video

HERE = Path(__file__).resolve().parent
HOST = os.environ.get("TYPECASE_VM", "typecase-vm")
FOLDER = "typecase-video"  # in the VM's home
ENVIRONMENT = ("DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus XDG_RUNTIME_DIR=/run/user/1000 "
               "XDG_CURRENT_DESKTOP=ubuntu:GNOME")
SCREEN = (1920, 1080)  # logical pixels of the VM's screen


class VM:
    """The connection to vm_remote.py in the VM, and the clock of the recording."""

    def __init__(self):
        subprocess.run(["scp", "-q", str(HERE / "vm_remote.py"), f"{HOST}:{FOLDER}/vm_remote.py"], check=True)
        self.process = subprocess.Popen(
            ["ssh", HOST, f"cd ~/{FOLDER} && env {ENVIRONMENT} python3 -W ignore vm_remote.py"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        if self.process.stdout.readline().strip() != "ready":
            raise RuntimeError("the remote desktop session in the VM did not start")
        self.began = None  # when the recording started (local clock)
        self.cuts: list[list[float]] = []  # [from, to] in seconds of the raw recording

    def send(self, *command):
        self.process.stdin.write(json.dumps(list(command)) + "\n")
        answer = self.process.stdout.readline().strip()
        if not answer.startswith("ok"):
            raise RuntimeError(f"{command[0]}: {answer}")
        _ok, _time, *rest = answer.split(" ", 2)
        return json.loads(rest[0]) if rest else None

    # --- what a step can do

    def key(self, keys: str) -> None:
        self.send("key", keys)

    def type(self, text: str, pause: float = 0.055) -> None:
        self.send("type", text, pause)

    def click(self, x: float, y: float, times: int = 1) -> None:
        self.send("click", x, y, times)

    def move(self, x: float, y: float) -> None:
        self.send("move", x, y)

    def text(self) -> str:
        return self.send("text")

    def wait_text(self, *endings: str, limit: float = 120) -> str:
        """Waits until the terminal ends with one of the endings; returns the one it found."""
        end = time.monotonic() + limit
        while time.monotonic() < end:
            shown = self.text().rstrip()
            for ending in endings:
                if shown.endswith(ending.rstrip()):
                    return ending
            time.sleep(0.2)
        raise TimeoutError(f"the terminal did not show {endings}")

    def wait_gone(self, name: str, limit: float = 600) -> None:
        self.send("wait_gone", name, limit)

    def wait_running(self, name: str, limit: float = 600) -> None:
        self.send("wait_running", name, limit)

    def wait_shell(self, command: str, limit: float = 600) -> None:
        """Waits until a shell command in the VM succeeds (a file is there, an app installed)."""
        self.send("wait_shell", command, limit)

    def zoom(self, rectangle=None, length: float = 1.2, margin: float = 0.04) -> float:
        """Glides the picture towards a rectangle of the screen (x, y, width, height in logical
        pixels), or back to the whole screen without one."""
        if rectangle is None:
            target = (1.0, 0.5, 0.5)
        else:
            left, top, width, height = rectangle
            w, h = width / SCREEN[0], height / SCREEN[1]
            z = min(videokit.MAX_ZOOM, 1 / max(w + 2 * margin, h + 2 * margin))
            target = (max(1.0, z), left / SCREEN[0] + w / 2, top / SCREEN[1] + h / 2)
        videokit._zooms.append((self.raw(), length, target))
        return length

    def cut(self) -> None:
        """From here on, the recording is left out of the video, until uncut()."""
        self.cuts.append([self.raw(), None])

    def uncut(self) -> None:
        self.cuts[-1][1] = self.raw()

    # --- the clock

    def raw(self) -> float:
        """Seconds of the recording so far."""
        return time.monotonic() - self.began

    def now(self) -> float:
        """Seconds of the video so far: the recording without its cuts."""
        raw = self.raw()
        return raw - sum((end if end is not None else raw) - start for start, end in self.cuts)

    def record(self, path: str) -> None:
        self.send("record", path)
        self.began = time.monotonic()

    def stop(self) -> None:
        self.send("stop")

    def close(self) -> None:
        try:
            self.send("quit")
        except Exception:
            pass
        self.process.wait(timeout=30)


def _shown(raw: float, cuts: list[list[float]]) -> float:
    """A time of the raw recording as a time of the video."""
    return raw - sum(min(raw, end) - start for start, end in cuts if raw > start)


def _record(scenes: list[Scene], work: Path, before) -> None:
    """Plays the scenes in the VM and records them; leaves work/screen.mkv (cuts removed) and
    work/take.json, so the video can be put together again without recording."""
    vm = VM()
    try:
        if before:
            before(vm)
        vm.record("screen.mkv")  # in ~/typecase-video
        time.sleep(1.0)
        for scene in scenes:
            scene.start = vm.raw()
            began = vm.now()
            if scene.steps:
                for delay in scene.steps(vm):
                    time.sleep(max(0.0, delay))
            left = scene.duration + GAP - (vm.now() - began)
            time.sleep(max(0.0, left) + scene.hold)
        vm.stop()
    finally:
        vm.close()
    subprocess.run(["scp", "-q", f"{HOST}:{FOLDER}/screen.mkv", str(work / "raw.mkv")], check=True)
    cuts = [(start, end) for start, end in vm.cuts if end and end - start > 0.1]
    _cut(work / "raw.mkv", work / "screen.mkv", cuts)
    for scene in scenes:
        scene.start = _shown(scene.start, cuts)
    videokit._zooms[:] = [(_shown(start, cuts), length, view) for start, length, view in videokit._zooms]
    (work / "take.json").write_text(json.dumps({"starts": [scene.start for scene in scenes], "zooms": videokit._zooms}))


def _cut(source: Path, target: Path, cuts: list[tuple[float, float]]) -> None:
    """Writes the recording without the cut stretches (nearly lossless, still at full size)."""
    if not cuts:
        source.rename(target)
        return
    keep, last = [], 0.0
    for start, end in sorted(cuts):
        keep.append(f"between(t,{last:.3f},{start:.3f})")
        last = end
    keep.append(f"gte(t,{last:.3f})")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-vf",
                    f"select='{'+'.join(keep)}',setpts=N/FRAME_RATE/TB", "-an",
                    "-c:v", "libx264", "-crf", "12", "-preset", "veryfast", str(target)], check=True)


def run(video: Video, scenes: list[Scene], before=None) -> None:
    """Like videokit.run, but the scenes play in the VM. TYPECASE_VIDEO_KEEP and
    TYPECASE_VIDEO_REUSE work the same way."""
    work, reused = videokit._work(video)
    voices = videokit.speak(scenes + videokit.OUTRO, videokit.LANGUAGE, work)
    if reused:
        videokit._restore(scenes, work)
    else:
        _record(scenes, work, before)
    folder = OUTPUT / video.name
    videokit.finish(video, work, videokit.assemble(scenes, voices, work / "screen.mkv", work, folder, video.name))


if __name__ == "__main__":  # try the connection: prints what the terminal shows
    connection = VM()
    print(connection.text())
    connection.close()
    sys.exit(0)
