from gi.repository import Gdk


def popup_at_cursor(window, w, h):

    display = Gdk.Display.get_default()
    seat = display.get_default_seat()

    pointer = seat.get_pointer()

    screen, x, y = pointer.get_position()

    monitor = display.get_monitor_at_point(x, y)

    geo = monitor.get_geometry()

    if x + w > geo.x + geo.width:
        x = geo.x + geo.width - w

    if y + h > geo.y + geo.height:
        y = geo.y + geo.height - h

    window.move(x, y)
