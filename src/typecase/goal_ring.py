import locale
import math
from gettext import gettext as _
from gettext import ngettext

from gi.repository import Adw, Graphene, Gtk

from .goal import fraction


def _number(n: int) -> str:
    return locale.format_string("%d", n, grouping=True)  # 1,234 instead of 1234 (depending on locale)


class ProgressRing(Gtk.Widget):
    """Circular progress indicator. Its color comes from the style (CSS classes accent/success),
    so it follows the accent color as well as light and dark mode."""

    __gtype_name__ = "TypecaseGoalRing"

    def __init__(self, size: int, thickness: float, **kwargs):
        super().__init__(css_classes=["accent"], **kwargs)
        self.size = size
        self.thickness = thickness
        self.value = 0.0
        self._animation = Adw.TimedAnimation(
            widget=self,
            value_from=0,
            value_to=0,
            duration=450,
            easing=Adw.Easing.EASE_OUT_CUBIC,
            target=Adw.CallbackAnimationTarget.new(self._set_value),
        )

    def show_progress(self, value: float, reached: bool, animate: bool = True) -> None:
        """Glide smoothly to the new value (libadwaita skips this when animations are turned off)."""
        self.set_css_classes(["success" if reached else "accent"])
        self._animation.pause()
        if animate and self.get_mapped():
            self._animation.set_value_from(self.value)
            self._animation.set_value_to(value)
            self._animation.play()
        else:
            self._set_value(value)

    def _set_value(self, value: float):
        self.value = value
        self.queue_draw()

    def do_measure(self, _orientation, _for_size):
        return self.size, self.size, -1, -1

    def do_snapshot(self, snapshot):
        width, height = self.get_width(), self.get_height()
        cr = snapshot.append_cairo(Graphene.Rect().init(0, 0, width, height))
        color = self.get_color()
        radius = min(width, height) / 2 - self.thickness / 2
        cx, cy = width / 2, height / 2
        cr.set_line_width(self.thickness)
        cr.set_source_rgba(color.red, color.green, color.blue, 0.15)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.stroke()
        if self.value > 0:
            cr.set_line_cap(1)  # round
            cr.set_source_rgba(color.red, color.green, color.blue, color.alpha)
            start = -math.pi / 2  # start at the top, clockwise
            cr.arc(cx, cy, radius, start, start + 2 * math.pi * min(self.value, 1.0))
            cr.stroke()


class GoalView(Gtk.Box):
    """Ring with the words written in the middle, below it the percentage and what is still missing.
    Once the goal is reached, the ring turns green."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=18, halign=Gtk.Align.CENTER)
        self.ring = ProgressRing(148, 12)
        self.words_label = Gtk.Label(css_classes=["title-1", "numeric"])
        self.goal_label = Gtk.Label(css_classes=["dim-label", "caption"])
        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        center.append(self.words_label)
        center.append(self.goal_label)
        overlay = Gtk.Overlay(child=self.ring, halign=Gtk.Align.CENTER)
        overlay.add_overlay(center)
        self.append(overlay)
        self.status_label = Gtk.Label(css_classes=["heading"], wrap=True, justify=Gtk.Justification.CENTER)
        self.append(self.status_label)

    def update(self, words: int, goal: int, animate: bool = True) -> None:
        target = fraction(words, goal)
        reached = words >= goal
        self.words_label.set_label(_number(words))
        self.goal_label.set_label(ngettext("of %(goal)s word", "of %(goal)s words", goal) % {"goal": _number(goal)})
        if reached:
            self.status_label.set_label(_("Goal reached"))
        else:
            missing = goal - words
            self.status_label.set_label(
                _("%(percent)d%%") % {"percent": int(target * 100)}
                + " · "
                + ngettext("%(count)s word to go", "%(count)s words to go", missing) % {"count": _number(missing)}
            )
        self.status_label.set_css_classes(["heading", "success" if reached else "dim-label"])
        self.ring.show_progress(target, reached, animate)


class GoalBadge(Gtk.Button):
    """Small floating card at the bottom right of the editor while the properties pane is closed:
    mini ring and "742 / 1,500". A click opens the properties pane."""

    def __init__(self):
        super().__init__(css_classes=["goal-badge"], tooltip_text=_("Writing Goal"), action_name="win.inspector")
        box = Gtk.Box(spacing=8)
        self.ring = ProgressRing(20, 3.5)
        self.label = Gtk.Label(css_classes=["numeric", "caption-heading"])
        box.append(self.ring)
        box.append(self.label)
        self.set_child(box)

    def update(self, words: int, goal: int, animate: bool = True) -> None:
        self.label.set_label(_("%(count)s / %(goal)s") % {"count": _number(words), "goal": _number(goal)})
        self.update_property([Gtk.AccessibleProperty.LABEL], [self.get_tooltip_text() + ": " + self.label.get_label()])
        self.ring.show_progress(fraction(words, goal), words >= goal, animate)
