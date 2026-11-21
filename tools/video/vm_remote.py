"""Runs in the Ubuntu VM: holds a Mutter remote desktop session, records the screen and carries
out commands read line by line from stdin (JSON lists), so a script elsewhere can drive the desktop.

    ["move", x, y]          pointer to logical pixels (the screen is 1920x1080 logical)
    ["click", x, y]         move there and click the left button; ["click", x, y, 2] double-clicks
    ["key", "Super_L"]      press and release a key (X keysym name); ["key", "Control_L+Alt_L+t"] for a chord
    ["type", "text"]        type text character by character
    ["record", "path.mkv"]  start recording;  ["stop"] ends the recording
    ["snap", "path.png"]    one frame as PNG (not while recording)
    ["text"]                the text of the terminal window, read through the accessibility interface
    ["wait_text", "[Y/n]", 60]   wait until the terminal shows the text (at its end), at most 60 s
    ["wait_gone", "apt", 300]    wait until no process of that name runs any more
    ["wait_running", "apt", 300] wait until a process of that name runs
    ["wait_shell", "test -f x", 300]  wait until a shell command succeeds
    ["quit"]
Every command answers with one line "ok <seconds since start>[ <result>]" or "error <message>"."""

import json
import subprocess
import sys
import time

import gi

gi.require_version("Gst", "1.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, Gdk, Gio, GLib, Gst

Gst.init(None)
bus = Gio.bus_get_sync(Gio.BusType.SESSION)
RD, SC = "org.gnome.Mutter.RemoteDesktop", "org.gnome.Mutter.ScreenCast"
SCALE = 2  # physical pixels per logical pixel
FPS = 30


def call(dest, path, iface, method, args=None, sig=None):
    return bus.call_sync(dest, path, iface, method, args, GLib.VariantType(sig) if sig else None, 0, -1, None).unpack()


(rd_path,) = call(RD, "/org/gnome/Mutter/RemoteDesktop", RD, "CreateSession", None, "(o)")
session_id = call(RD, rd_path, "org.freedesktop.DBus.Properties", "Get",
                  GLib.Variant("(ss)", (RD + ".Session", "SessionId")))[0]
(sc_path,) = call(SC, "/org/gnome/Mutter/ScreenCast", SC, "CreateSession",
                  GLib.Variant("(a{sv})", ({"remote-desktop-session-id": GLib.Variant("s", session_id)},)), "(o)")
(stream_path,) = call(SC, sc_path, SC + ".Session", "RecordMonitor",
                      GLib.Variant("(sa{sv})", ("", {"cursor-mode": GLib.Variant("u", 1)})), "(o)")
loop = GLib.MainLoop()
node = {}
bus.signal_subscribe(SC, SC + ".Stream", "PipeWireStreamAdded", stream_path, None, 0,
                     lambda *a: (node.setdefault("id", a[5].unpack()[0]), loop.quit()))
call(RD, rd_path, RD + ".Session", "Start")
GLib.timeout_add_seconds(10, loop.quit)
loop.run()
time.sleep(0.5)
objects = json.loads(subprocess.run(["pw-dump"], capture_output=True, text=True).stdout)
serial = next(o["info"]["props"]["object.serial"] for o in objects if o["id"] == node["id"])
began = time.monotonic()
recording = None


def session(method, args):
    call(RD, rd_path, RD + ".Session", method, args)


def move(x, y):
    session("NotifyPointerMotionAbsolute", GLib.Variant("(sdd)", (stream_path, x * SCALE, y * SCALE)))


def key(name, pressed):
    session("NotifyKeyboardKeysym", GLib.Variant("(ub)", (Gdk.keyval_from_name(name), pressed)))


def run(pipeline):
    pipe = Gst.parse_launch(pipeline)
    pipe.set_state(Gst.State.PLAYING)
    return pipe


def terminal_text():
    """The text of the first terminal widget of Ptyxis, through AT-SPI."""
    desktop = Atspi.get_desktop(0)
    for index in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(index)
        if app and (app.get_name() or "").lower().startswith("ptyxis"):
            found = find_role(app, Atspi.Role.TERMINAL, 0)
            if found:
                return Atspi.Text.get_text(found, 0, Atspi.Text.get_character_count(found))
    return ""


def find_role(node, role, depth):
    if depth > 25 or node is None:
        return None
    if node.get_role() == role:
        return node
    for index in range(node.get_child_count()):
        found = find_role(node.get_child_at_index(index), role, depth + 1)
        if found:
            return found
    return None


def running(name):
    return subprocess.run(["pgrep", "-x", name], capture_output=True).returncode == 0


def wait(condition, limit):
    end = time.monotonic() + limit
    while not condition():
        if time.monotonic() > end:
            raise TimeoutError("waited too long")
        time.sleep(0.15)


def handle(command):
    global recording
    kind, *args = command
    if kind == "text":
        return terminal_text()
    if kind == "wait_text":
        wait(lambda: terminal_text().rstrip().endswith(args[0]), args[1] if len(args) > 1 else 60)
    elif kind == "wait_gone":
        wait(lambda: not running(args[0]), args[1] if len(args) > 1 else 300)
    elif kind == "wait_running":
        wait(lambda: running(args[0]), args[1] if len(args) > 1 else 300)
    elif kind == "wait_shell":
        wait(lambda: subprocess.run(["bash", "-c", args[0]], capture_output=True).returncode == 0,
             args[1] if len(args) > 1 else 300)
    elif kind == "move":
        move(*args)
    elif kind == "click":  # ["click", x, y, 2] double-clicks
        move(args[0], args[1])
        time.sleep(0.05)
        for _ in range(args[2] if len(args) > 2 else 1):
            for pressed in (True, False):
                session("NotifyPointerButton", GLib.Variant("(ib)", (0x110, pressed)))  # BTN_LEFT
                time.sleep(0.04)
    elif kind == "key":
        names = args[0].split("+")
        for name in names:
            key(name, True)
        for name in reversed(names):
            key(name, False)
    elif kind == "type":
        for char in args[0]:
            name = {"\n": "Return", " ": "space"}.get(char) or Gdk.keyval_name(Gdk.unicode_to_keyval(ord(char)))
            key(name, True)
            key(name, False)
            time.sleep(args[1] if len(args) > 1 else 0.06)
    elif kind == "record":
        recording = run(f"pipewiresrc target-object={serial} do-timestamp=true keepalive-time=33 ! videorate ! "
                        f"video/x-raw,framerate={FPS}/1 ! videoconvert ! video/x-raw,format=I420 ! "
                        f"x264enc speed-preset=ultrafast qp-max=18 tune=zerolatency ! matroskamux ! filesink location={args[0]}")
    elif kind == "stop":
        recording.send_event(Gst.Event.new_eos())
        recording.get_bus().timed_pop_filtered(30 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
        recording.set_state(Gst.State.NULL)
        recording = None
    elif kind == "snap":
        pipe = run(f"pipewiresrc target-object={serial} ! videoconvert ! pngenc snapshot=true ! filesink location={args[0]}")
        pipe.get_bus().timed_pop_filtered(10 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
        pipe.set_state(Gst.State.NULL)
    elif kind == "quit":
        return False
    else:
        raise ValueError(f"unknown command {kind}")
    return True


print("ready", flush=True)
for line in sys.stdin:
    try:
        result = handle(json.loads(line))
        extra = f" {json.dumps(result)}" if isinstance(result, str) else ""
        print(f"ok {time.monotonic() - began:.3f}{extra}", flush=True)
        if result is False:
            break
    except Exception as error:  # report and keep the session
        print(f"error {error}", flush=True)
if recording:
    handle(["stop"])
call(RD, rd_path, RD + ".Session", "Stop")
