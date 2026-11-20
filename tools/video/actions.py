"""Small helpers for the video scripts that act like a person using the app."""

from videokit import name


def node(win, english):
    """The library row with this name (in the language of the run)."""
    wanted = name(english)
    for i in range(win.tree_model.get_n_items()):
        row = win.tree_model.get_item(i)
        if row.get_item().node.name == wanted:
            return i, row
    raise LookupError(wanted)


def select(win, english):
    win.selection.set_selected(node(win, english)[0])


def labels(win):
    """The labels of the rows the library shows."""
    from gi.repository import Gtk

    def walk(widget):
        child = widget.get_first_child()
        while child is not None:
            yield child
            yield from walk(child)
            child = child.get_next_sibling()

    return [widget for widget in walk(win.list_view) if isinstance(widget, Gtk.Label) and widget.get_mapped()]


def label_of(win, english):
    """The label that shows the row, to point at it."""
    for widget in labels(win):
        if widget.get_label() == name(english):
            return widget
    raise LookupError(english)


def library_rows(win):
    """The rows the sidebar shows, as a rectangle in the window."""
    boxes = [label.compute_bounds(win)[1] for label in labels(win)]
    top = min(b.get_y() for b in boxes) - 12
    bottom = max(b.get_y() + b.get_height() for b in boxes) + 12
    right = max(b.get_x() + b.get_width() for b in boxes) + 48  # with the goal rings
    return (0, top, right, bottom - top)


def menu_area(win, english):
    """The row and the menu that opens next to it (the menu is a window of its own)."""
    _found, row = label_of(win, english).compute_bounds(win)
    return (0, row.get_y() - 8, row.get_x() + row.get_width() * 0.6 + win.row_menu.get_width(), win.row_menu.get_height() + row.get_height() + 16)


def right_click(win, english):
    """Selects the row and opens its menu, as a right-click does."""
    from gi.repository import Gdk, Graphene

    select(win, english)
    label = label_of(win, english)
    _found, point = label.compute_point(win.list_view, Graphene.Point().init(label.get_width() * 0.6, label.get_height() / 2))
    rect = Gdk.Rectangle()
    rect.x, rect.y, rect.width, rect.height = int(point.x), int(point.y), 1, 1
    win.row_menu.set_pointing_to(rect)
    win.row_menu.popup()


def choose(box, index):
    child = box.get_child_at_index(index)
    child.grab_focus()
    box.select_child(child)


def walk_to(box, start, target, pause=0.18):
    """Moves the selection step by step, the way the arrow keys do."""
    step = 1 if target >= start else -1
    for index in range(start, target + step, step):
        choose(box, index)
        yield pause


def set_look(win, english, icon, color):
    from typecase import looks

    win._set_look(node(win, english)[1].get_item().node, looks.Look.of(icon, color))
