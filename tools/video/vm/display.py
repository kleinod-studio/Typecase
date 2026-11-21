"""Sets the VM's only monitor to a mode and scale: python3 display.py 3840x2160@60.000 2"""
import sys

from gi.repository import Gio, GLib

bus = Gio.bus_get_sync(Gio.BusType.SESSION)
NAME = "org.gnome.Mutter.DisplayConfig"
serial, monitors, logical, _props = bus.call_sync(NAME, "/org/gnome/Mutter/DisplayConfig", NAME, "GetCurrentState",
                                                  None, None, 0, -1, None).unpack()
connector = monitors[0][0][0]
mode, scale = sys.argv[1], float(sys.argv[2])
config = [(0, 0, scale, 0, True, [(connector, mode, {})])]
bus.call_sync(NAME, "/org/gnome/Mutter/DisplayConfig", NAME, "ApplyMonitorsConfig",
              GLib.Variant("(uua(iiduba(ssa{sv}))a{sv})", (serial, 2, config, {})), None, 0, -1, None)
print("set", connector, mode, scale)
