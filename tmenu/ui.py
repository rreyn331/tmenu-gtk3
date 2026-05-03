import os
import sys
import subprocess
import shlex
import shutil
import signal
import tempfile
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf

# Attempt to load GtkLayerShell for Wayland positioning
try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell
    HAS_LAYER_SHELL = True
except (ValueError, ImportError):
    HAS_LAYER_SHELL = False

# Path Fix
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path: sys.path.insert(0, current_dir)

try:
    from . import cache, config, fuzzy, power
except (ImportError, ValueError):
    import cache, config, fuzzy, power

CATEGORY_DATA = {
    "All Applications": "applications-all",
    "Accessories": "applications-accessories",
    "Development": "applications-development",
    "Education": "applications-education",
    "Games": "applications-games",
    "Graphics": "applications-graphics",
    "Internet": "applications-internet",
    "Multimedia": "applications-multimedia",
    "Office": "applications-office",
    "Settings": "preferences-system",
    "System": "applications-system",
    "Other": "applications-other"
}

class TMenu:
    WIDTH, HEIGHT, ICON_SIZE = 480, 520, 28

    def __init__(self, force_refresh=False):
        refresh = force_refresh or "--refresh" in sys.argv
        self.apps = cache.load_cache(force_refresh=refresh)
        self.config = config.load()  
        
        display = Gdk.Display.get_default()
        self.is_wayland = 'Wayland' in type(display).__name__
        
        self.window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.window.set_wmclass("tmenu", "tmenu")
        self.window.set_decorated(False)
        self.window.set_keep_above(True)
        self.window.set_skip_taskbar_hint(True)
        self.window.set_skip_pager_hint(True)

        self.window.add_events(Gdk.EventMask.FOCUS_CHANGE_MASK | 
                               Gdk.EventMask.BUTTON_PRESS_MASK)
        
        if self.is_wayland:
            if HAS_LAYER_SHELL:
                GtkLayerShell.init_for_window(self.window)
                GtkLayerShell.set_layer(self.window, GtkLayerShell.Layer.OVERLAY)
                GtkLayerShell.set_keyboard_mode(self.window, GtkLayerShell.KeyboardMode.ON_DEMAND)
        else:
            self.window.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)

        self.window.set_size_request(self.WIDTH, self.HEIGHT)
        self.build_ui()
        
        self.window.connect("focus-out-event", self.on_focus_out)
        self.window.connect("key-press-event", self.on_key)
        self.window.connect("button-press-event", self.on_window_click)

    def get_scaled_icon(self, name, size):
        try:
            if name and name.startswith("/") and os.path.exists(name):
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(name, size, size, True)
                return Gtk.Image.new_from_pixbuf(pb)
            img = Gtk.Image.new_from_icon_name(name or "application-x-executable", Gtk.IconSize.MENU)
            img.set_pixel_size(size)
            return img
        except:
            return Gtk.Image.new_from_icon_name("application-x-executable", Gtk.IconSize.MENU)

    def build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, border_width=10)
        self.window.add(vbox)
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
        vbox.pack_start(hbox, True, True, 0)

        sidebar_width = self.config.get("layout", {}).get("sidebar_width", 180)
        self.cat_list = Gtk.ListBox()
        self.cat_list.connect("row-selected", lambda lb, row: self.on_cat_selected(row))
        
        self.scroll_cat_win = Gtk.ScrolledWindow(width_request=sidebar_width)
        self.scroll_cat_win.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroll_cat_win.add(self.cat_list)
        hbox.pack_start(self.scroll_cat_win, False, False, 0)

        self.app_list = Gtk.ListBox()
        self.app_list.connect("row-activated", self.on_app_clicked)
        self.scroll_app_win = Gtk.ScrolledWindow()
        self.scroll_app_win.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroll_app_win.add(self.app_list)
        hbox.pack_start(self.scroll_app_win, True, True, 0)

        self.power_commands_data = [
            {"Name": "Lock Screen", "Icon": "system-lock-screen", "action": "lock", "is_power": True},
            {"Name": "Logout", "Icon": "system-log-out", "action": "logout", "is_power": True},
            {"Name": "Hibernate", "Icon": "system-suspend-hibernate", "action": "hibernate", "is_power": True},
            {"Name": "Reboot", "Icon": "system-reboot", "action": "reboot", "is_power": True},
            {"Name": "Shutdown", "Icon": "system-shutdown", "action": "shutdown", "is_power": True}
        ]
        for p in self.power_commands_data: self.create_app_row(p, visible=False)
        for a in self.apps: self.create_app_row(a)
        self.terminal_row = self.create_app_row({"Name": "Terminal Run", "Icon": "utilities-terminal", "is_terminal": True}, visible=False)

        bottom_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, margin_top=10)
        vbox.pack_end(bottom_bar, False, False, 0)
        self.power_box = Gtk.Box(spacing=4)
        bottom_bar.pack_start(self.power_box, False, False, 0)

        self.search_entry = Gtk.Entry(placeholder_text="Search...", hexpand=True)
        self.search_entry.connect("changed", self.on_search)
        bottom_bar.pack_start(self.search_entry, True, True, 0)

        self.setup_sidebar()
        self.load_power_buttons()
        self.active_list = self.app_list

    def create_app_row(self, app, visible=True):
        row = Gtk.ListBoxRow(); row.app_data = app
        box = Gtk.Box(spacing=10, border_width=5)
        icon_name = app.get("Icon") or "application-x-executable"
        box.pack_start(self.get_scaled_icon(icon_name, self.ICON_SIZE), False, False, 0)
        row.label_widget = Gtk.Label(label=app.get("Name", "Unknown"), xalign=0)
        box.pack_start(row.label_widget, True, True, 0)
        row.add(box); self.app_list.add(row)
        if visible: row.show_all()
        else: row.hide()
        return row

    def on_search(self, entry):
        txt = entry.get_text().strip()
        txt_lower = txt.lower()
        
        if not txt:
            self.on_cat_selected(self.cat_list.get_selected_row())
            return
        
        matches = fuzzy.search(txt_lower, self.apps)
        match_names = {m["Name"] for m in matches}

        for row in self.app_list.get_children():
            if row == self.terminal_row: continue
            name = row.app_data.get("Name", "").lower()
            should_show = (txt_lower in name or row.app_data.get("Name") in match_names)
            row.set_visible(should_show)

        cmd_base = txt.split()[0] if txt else ""
        if cmd_base and shutil.which(cmd_base):
            self.terminal_row.set_visible(True)
            self.terminal_row.app_data["Exec"] = txt
            self.terminal_row.label_widget.set_text(f"Run: {txt} (in Terminal)")
        else:
            self.terminal_row.set_visible(False)
            
        self.select_first_visible(self.app_list)

    def on_cat_selected(self, row):
        if not row or self.search_entry.get_text().strip(): return
        target = row.cat_name
        for child in self.app_list.get_children():
            if child == self.terminal_row: 
                child.set_visible(False)
                continue
            data = child.app_data
            cats = data.get("Categories") or []
            if isinstance(cats, str): cats = [cats]
            is_vis = (target == "All Applications" or target in cats)
            child.set_visible(is_vis and not data.get("is_power"))
        self.select_first_visible(self.app_list)

    def setup_sidebar(self):
        self.add_sidebar_row("All Applications", CATEGORY_DATA["All Applications"])
        found_cats = set()
        for a in self.apps:
            cats = a.get("Categories", [])
            if isinstance(cats, list): found_cats.update(cats)
            else: found_cats.add(cats)
            
        for n, i in CATEGORY_DATA.items():
            if n != "All Applications" and n in found_cats:
                self.add_sidebar_row(n, i)
                
        first = self.cat_list.get_children()[0]
        self.cat_list.select_row(first)
        self.on_cat_selected(first)

    def add_sidebar_row(self, name, icon_name):
        row = Gtk.ListBoxRow(); row.cat_name = name
        eb = Gtk.EventBox()
        box = Gtk.Box(spacing=12, border_width=6)
        box.pack_start(self.get_scaled_icon(icon_name, 20), False, False, 0)
        box.pack_start(Gtk.Label(label=name, xalign=0), True, True, 0)
        eb.add(box); row.add(eb)
        eb.connect("enter-notify-event", lambda w, e: self.cat_list.select_row(row))
        self.cat_list.add(row)
        row.show_all()

    def on_app_clicked(self, lb, row):
        if not row or not hasattr(row, 'app_data'): return
        data = row.app_data
        
        if data.get("is_power"):
            if hasattr(power, data.get("action")): getattr(power, data.get("action"))()
        else:
            cmd = data.get("Exec", "")
            if data.get("is_terminal"):
                term = shutil.which("xfce4-terminal") or shutil.which("gnome-terminal") or \
                       shutil.which("kitty") or shutil.which("alacritty") or "xterm"
                
                # Logic to add the command to bash history so Up arrow works later
                hist_file = os.path.expanduser("~/.bash_history")
                
                # We wrap the command to:
                # 1. Print it cleanly (the 'echo -e' part)
                # 2. Add it to the physical history file
                # 3. Execute the command
                # 4. Start a shell and load that history file
                wrapped_cmd = (
                    f"echo -e '\\033[1;32m➜\\033[0m \\033[1;34m~\\033[0m $ {cmd}'; "
                    f"echo '{cmd}' >> {hist_file}; "
                    f"{cmd}; "
                    f"echo; echo 'Command finished. Press Enter to drop to shell...'; read; "
                    f"exec bash --init-file <(echo 'history -r {hist_file}')"
                )
                
                if "xfce4-terminal" in term:
                    args = [term, "--command", f"bash -c \"{wrapped_cmd}\""]
                elif "gnome-terminal" in term:
                    args = [term, "--", "bash", "-c", wrapped_cmd]
                else:
                    args = [term, "-e", "bash", "-c", wrapped_cmd]
                
                subprocess.Popen(args, start_new_session=True)
            else:
                args = [a for a in shlex.split(cmd) if not a.startswith('%')]
                subprocess.Popen(args, start_new_session=True)
                
        self.hide_menu()

    def navigate(self, step):
        vis = [r for r in self.active_list.get_children() if r.get_visible()]
        if not vis: return
        curr = self.active_list.get_selected_row()
        idx = vis.index(curr) if curr in vis else 0
        new_idx = max(0, min(idx + step, len(vis) - 1))
        target = vis[new_idx]
        self.active_list.select_row(target)
        adj = self.scroll_app_win.get_vadjustment() if self.active_list == self.app_list else self.scroll_cat_win.get_vadjustment()
        alloc = target.get_allocation()
        adj.clamp_page(alloc.y, alloc.y + alloc.height)

    def on_key(self, w, e):
        k = e.keyval
        if k == Gdk.KEY_Escape: self.hide_menu(); return True
        if k == Gdk.KEY_Up: self.navigate(-1); return True
        if k == Gdk.KEY_Down: self.navigate(1); return True
        if k == Gdk.KEY_Left: 
            self.active_list = self.cat_list
            self.navigate(0)
            return True
        if k == Gdk.KEY_Right: 
            self.active_list = self.app_list
            self.navigate(0)
            return True
        if k == Gdk.KEY_Return:
            row = self.active_list.get_selected_row()
            if self.active_list == self.cat_list:
                self.active_list = self.app_list
                self.navigate(0)
            elif row:
                self.on_app_clicked(None, row)
            return True
        return False

    def show_menu(self, *args):
        self.set_smart_position()
        self.window.show_all()
        if not self.is_wayland:
            GLib.timeout_add(100, self._do_x11_grab)
        GLib.timeout_add(50, self.force_focus)
        return True

    def _do_x11_grab(self):
        win = self.window.get_window()
        if win:
            seat = Gdk.Display.get_default().get_default_seat()
            status = seat.grab(win, Gdk.SeatCapabilities.ALL, True, None, None, None)
            return status != Gdk.GrabStatus.SUCCESS
        return False

    def hide_menu(self, *args):
        if not self.window.get_visible(): return False
        if not self.is_wayland:
            Gdk.Display.get_default().get_default_seat().ungrab()
        self.window.hide()
        self.search_entry.set_text("")
        if not getattr(self, "is_daemon", False): self.true_quit()
        return False

    def on_window_click(self, widget, event):
        alloc = self.window.get_allocation()
        if event.x < 0 or event.x > alloc.width or event.y < 0 or event.y > alloc.height:
            self.hide_menu()
            return True
        return False

    def on_focus_out(self, widget, event):
        self.hide_menu()
        return False

    def load_power_buttons(self):
        for b in self.config.get("power_buttons", []):
            btn = Gtk.Button(relief=Gtk.ReliefStyle.NONE)
            btn.set_image(self.get_scaled_icon(b.get("icon"), self.ICON_SIZE))
            btn.connect("clicked", lambda w, a=b.get("action"): self.launch_power(a))
            self.power_box.pack_start(btn, False, False, 0)
        self.power_box.show_all()

    def launch_power(self, action):
        if hasattr(power, action): getattr(power, action)()
        self.hide_menu()

    def set_smart_position(self):
        layout = self.config.get("layout", {})
        margin = layout.get("screen_margin", 10)
        vert, horiz = layout.get("vertical_position", "bottom"), layout.get("horizontal_position", "left")
        if self.is_wayland and HAS_LAYER_SHELL:
            GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.TOP if vert == "top" else GtkLayerShell.Edge.BOTTOM, True)
            GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.LEFT if horiz == "left" else GtkLayerShell.Edge.RIGHT, True)
            GtkLayerShell.set_margin(self.window, GtkLayerShell.Edge.BOTTOM if vert == "bottom" else GtkLayerShell.Edge.TOP, margin)
            GtkLayerShell.set_margin(self.window, GtkLayerShell.Edge.LEFT if horiz == "left" else GtkLayerShell.Edge.RIGHT, margin)
        else:
            mon = Gdk.Display.get_default().get_primary_monitor().get_geometry()
            x = mon.x + margin if horiz == "left" else mon.x + mon.width - self.WIDTH - margin
            y = mon.y + margin if vert == "top" else mon.y + mon.height - self.HEIGHT - margin
            self.window.move(x, y)

    def select_first_visible(self, lb):
        for r in lb.get_children():
            if r.get_visible():
                lb.select_row(r)
                break

    def true_quit(self):
        try: Gtk.main_quit()
        except: pass
        sys.exit(0)

    def force_focus(self):
        self.window.present()
        self.search_entry.grab_focus()
        return False

    def run(self):
        signal.signal(signal.SIGINT, lambda s, f: self.true_quit())
        self.show_menu()
        Gtk.main()

if __name__ == "__main__":
    TMenu().run()