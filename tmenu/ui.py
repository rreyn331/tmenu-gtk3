import os
import sys
import subprocess
import shlex
import shutil
import signal
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

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
        
        # 1. Bulletproof Display Detection
        # We ask GTK directly what display server it is rendering to
        display = Gdk.Display.get_default()
        self.is_wayland = 'Wayland' in type(display).__name__
        self.display_type = "wayland" if self.is_wayland else "x11"
        
        self.icon_theme = Gtk.IconTheme.get_default()
        self.pixbuf_cache = {}
        self.positioned = False

        self.window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.window.set_wmclass("tmenu", "tmenu")
        self.window.set_decorated(False)
        self.window.set_keep_above(True)
        self.window.set_skip_taskbar_hint(True)
        self.window.set_skip_pager_hint(True)
        
        # X11: Use POPUP_MENU, Wayland: Use UTILITY
        if self.is_wayland:
            self.window.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        else:
            self.window.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)
            
        # Initialize Layer Shell ONLY if strictly on Wayland
        if self.is_wayland and HAS_LAYER_SHELL:
            GtkLayerShell.init_for_window(self.window)
            GtkLayerShell.set_layer(self.window, GtkLayerShell.Layer.OVERLAY)
            GtkLayerShell.set_keyboard_mode(self.window, GtkLayerShell.KeyboardMode.ON_DEMAND)
        
        # 2. Strict Size Enforcement
        # Prevents Wayland or XWayland from squashing the menu
        self.window.set_size_request(self.WIDTH, self.HEIGHT)
        self.window.set_position(Gtk.WindowPosition.NONE)
        
        self.active_list = None
        self.build_ui()
        
        self.window.connect("focus-out-event", lambda w, e: self.quit())
        self.window.connect("key-press-event", self.on_key)
        self.window.connect("button-press-event", self.on_window_click)
        self.window.connect("map-event", self.on_window_mapped)
        self.window.connect("delete-event", lambda w, e: self.quit() or True)

    def quit(self):
        try:
            Gtk.main_quit()
        except:
            pass
        sys.exit(0)

    def on_window_click(self, widget, event):
        return False

    def on_window_mapped(self, widget, event):
        if not self.positioned:
            self.positioned = True
            GLib.timeout_add(50, self.set_smart_position)
        return False

    def get_scaled_icon(self, name, size):
        cache_key = f"{name}_{size}"
        if cache_key in self.pixbuf_cache: 
            return Gtk.Image.new_from_pixbuf(self.pixbuf_cache[cache_key])
        try:
            info = self.icon_theme.lookup_icon(name or "application-x-executable", size, 0)
            if info:
                pb = info.load_icon().scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)
                self.pixbuf_cache[cache_key] = pb
                return Gtk.Image.new_from_pixbuf(pb)
        except: pass
        return Gtk.Image.new_from_icon_name("application-x-executable", Gtk.IconSize.MENU)

    def build_ui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, border_width=10)
        self.window.add(vbox)
        
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
        vbox.pack_start(hbox, True, True, 0)

        sidebar_width = self.config.get("layout", {}).get("sidebar_width", 180)
        self.cat_list = Gtk.ListBox()
        self.scroll_cat_win = Gtk.ScrolledWindow(width_request=sidebar_width)
        self.scroll_cat_win.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroll_cat_win.add(self.cat_list)
        hbox.pack_start(self.scroll_cat_win, False, False, 0)

        self.app_list = Gtk.ListBox()
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

        spacer = Gtk.Box(width_request=10)
        bottom_bar.pack_start(spacer, False, False, 0)

        self.search_entry = Gtk.Entry(placeholder_text="Search...", width_chars=25)
        self.search_entry.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "edit-clear-symbolic")
        self.search_entry.connect("changed", self.on_search)
        self.search_entry.connect("icon-press", lambda e, p, ev: e.set_text(""))
        bottom_bar.pack_start(self.search_entry, True, True, 0)

        self.setup_sidebar()
        self.load_power_buttons()
        self.active_list = self.app_list

    def create_app_row(self, app, visible=True):
        row = Gtk.ListBoxRow(); row.app_data = app
        box = Gtk.Box(spacing=10, border_width=5)
        icon_name = app.get("Icon") or app.get("icon")
        box.pack_start(self.get_scaled_icon(icon_name, self.ICON_SIZE), False, False, 0)
        row.label_widget = Gtk.Label(label=str(app.get("Name") or "Unknown"), xalign=0)
        box.pack_start(row.label_widget, True, True, 0)
        row.add(box)
        row.connect("button-press-event", lambda r, e: self.launch_item(r.app_data) if e.button == 1 else None)
        self.app_list.add(row)
        if not visible: row.hide()
        return row

    def on_search(self, entry):
        txt = entry.get_text().strip()
        if not txt:
            self.on_cat_selected(self.cat_list.get_selected_row())
            return

        matches = fuzzy.search(txt, self.apps)
        match_names = {m["Name"] for m in matches}
        p_matches = {p["Name"] for p in self.power_commands_data if txt.lower() in p["Name"].lower()}
        
        found = False
        for row in self.app_list.get_children():
            if row == self.terminal_row: row.hide(); continue
            name = row.app_data.get("Name")
            if name in match_names or name in p_matches:
                row.show_all(); found = True
            else: row.hide()

        base_cmd = txt.split()[0] if txt else ""
        if not found and base_cmd and shutil.which(base_cmd):
            self.terminal_row.show_all()
            self.terminal_row.app_data["Exec"] = txt 
            self.terminal_row.label_widget.set_text(f"Run: {txt}")
        else:
            self.terminal_row.hide()

        self.select_first_visible(self.app_list)

    def launch_item(self, data):
        if data.get("is_power"):
            act = data.get("action")
            if hasattr(power, act): 
                try:
                    getattr(power, act)()
                except:
                    pass
        elif data.get("is_terminal"):
            cmd = data.get("Exec", "")
            try:
                subprocess.Popen(["x-terminal-emulator", "-e", f"bash -c {shlex.quote(cmd + '; exec bash')}"], start_new_session=True)
            except:
                pass
        else:
            try:
                cmd = data.get("Exec", "")
                args = [a for a in shlex.split(cmd) if not a.startswith('%')]
                subprocess.Popen(args, start_new_session=True)
            except: 
                pass
        self.quit()

    def load_power_buttons(self):
        for child in self.power_box.get_children(): self.power_box.remove(child)
        for b in self.config.get("power_buttons", []):
            name = b.get("name") or b.get("action", "").capitalize()
            btn = Gtk.Button(relief=Gtk.ReliefStyle.NONE)
            btn.set_image(self.get_scaled_icon(b.get("icon"), self.ICON_SIZE))
            btn.set_tooltip_text(name)
            btn.connect("clicked", lambda w, a=b.get("action"): self.launch_item({"is_power": True, "action": a}))
            self.power_box.pack_start(btn, False, False, 0)
        self.power_box.show_all()

    def setup_sidebar(self):
        self.add_sidebar_row("All Applications", CATEGORY_DATA["All Applications"])
        for n, i in CATEGORY_DATA.items():
            if n != "All Applications" and any(a.get("Categories") == n for a in self.apps):
                self.add_sidebar_row(n, i)
        self.cat_list.select_row(self.cat_list.get_children()[0])

    def add_sidebar_row(self, name, icon_name):
        row = Gtk.ListBoxRow(); row.cat_name = name
        eb = Gtk.EventBox()
        eb.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK)
        box = Gtk.Box(spacing=12, border_width=6)
        box.pack_start(self.get_scaled_icon(icon_name, 20), False, False, 0)
        box.pack_start(Gtk.Label(label=name, xalign=0), True, True, 0)
        eb.add(box); row.add(eb)
        eb.connect("enter-notify-event", lambda w, e: self._on_sidebar_hover(row))
        self.cat_list.add(row)

    def _on_sidebar_hover(self, row):
        self.cat_list.select_row(row)
        self.active_list = self.cat_list
        self.on_cat_selected(row)

    def on_cat_selected(self, row):
        if not row or self.search_entry.get_text().strip(): return
        target = row.cat_name
        for child in self.app_list.get_children():
            if child == self.terminal_row: child.hide(); continue
            is_match = target == "All Applications" or child.app_data.get("Categories") == target
            child.show_all() if (is_match and not child.app_data.get("is_power")) else child.hide()

    def select_first_visible(self, listbox):
        for r in listbox.get_children():
            if r.get_visible():
                listbox.select_row(r)
                break

    def on_key(self, w, e):
        k = e.keyval
        if k == Gdk.KEY_Escape: self.quit(); return True
        if k == Gdk.KEY_Left:
            self.active_list = self.cat_list
            self.select_first_visible(self.cat_list)
            return True
        if k == Gdk.KEY_Right:
            self.active_list = self.app_list
            self.select_first_visible(self.app_list)
            return True
        if k in [Gdk.KEY_Up, Gdk.KEY_Down]:
            self.navigate(1 if k == Gdk.KEY_Down else -1)
            if self.active_list == self.cat_list:
                self.on_cat_selected(self.cat_list.get_selected_row())
            return True
        if k == Gdk.KEY_Return:
            s = self.active_list.get_selected_row()
            if s and hasattr(s, 'app_data'): self.launch_item(s.app_data)
            return True
        if Gdk.keyval_to_unicode(k) > 31:
            if not self.search_entry.is_focus():
                self.search_entry.grab_focus()
                self.search_entry.set_position(-1)
        return False

    def navigate(self, step):
        vis = [r for r in self.active_list.get_children() if r.get_visible()]
        if not vis: return
        curr = self.active_list.get_selected_row()
        idx = vis.index(curr) if curr in vis else -1
        new_idx = max(0, min(idx + step, len(vis) - 1))
        target_row = vis[new_idx]
        self.active_list.select_row(target_row)
        adj = self.scroll_app_win.get_vadjustment() if self.active_list == self.app_list else self.scroll_cat_win.get_vadjustment()
        alloc = target_row.get_allocation()
        adj.clamp_page(alloc.y, alloc.y + alloc.height)

    def get_position_from_args(self):
        if "--left" in sys.argv: return "left"
        elif "--right" in sys.argv: return "right"
        elif "--center" in sys.argv: return "center"
        elif "--top" in sys.argv: return "top"
        elif "--bottom" in sys.argv: return "bottom"
        else: return self.config.get("layout", {}).get("horizontal_position", "left")

    def set_smart_position(self):
        """Position the window dynamically for Wayland or X11"""
        try:
            layout = self.config.get("layout", {})
            vertical_position = layout.get("vertical_position", "bottom")
            horizontal_position = self.get_position_from_args()
            screen_margin = layout.get("screen_margin", 10)
            offset_x = layout.get("offset_x", 0)
            offset_y = layout.get("offset_y", 0)
            
            # WAYLAND POSITIONING (Layer Shell)
            if self.is_wayland and HAS_LAYER_SHELL:
                for edge in [GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM, GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT]:
                    GtkLayerShell.set_anchor(self.window, edge, False)

                if vertical_position == "top":
                    GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.TOP, True)
                    GtkLayerShell.set_margin(self.window, GtkLayerShell.Edge.TOP, screen_margin + offset_y) 
                else: 
                    GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.BOTTOM, True)
                    GtkLayerShell.set_margin(self.window, GtkLayerShell.Edge.BOTTOM, max(0, screen_margin - offset_y)) 

                if horizontal_position == "left":
                    GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.LEFT, True)
                    GtkLayerShell.set_margin(self.window, GtkLayerShell.Edge.LEFT, screen_margin + offset_x)
                elif horizontal_position == "right":
                    GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.RIGHT, True)
                    GtkLayerShell.set_margin(self.window, GtkLayerShell.Edge.RIGHT, max(0, screen_margin - offset_x))

                self.window.present()
                self.search_entry.grab_focus()
                return False

            # X11 POSITIONING (Absolute Coordinates Fallback)
            display = Gdk.Display.get_default()
            monitor = None
            try:
                seat = display.get_default_seat()
                pointer = seat.get_pointer()
                screen, x, y = pointer.get_position()
                monitor = display.get_monitor_at_point(x, y)
            except:
                monitor = display.get_primary_monitor()
            
            if not monitor:
                monitors = [display.get_monitor(i) for i in range(display.get_n_monitors())]
                monitor = monitors[0] if monitors else None
            
            if not monitor:
                self.window.present()
                self.search_entry.grab_focus()
                return False
            
            geom = monitor.get_geometry()
            
            if horizontal_position == "left":
                x = geom.x + screen_margin + offset_x
            elif horizontal_position == "right":
                x = geom.x + geom.width - self.WIDTH - screen_margin + offset_x
            else:  
                x = geom.x + (geom.width // 2) - (self.WIDTH // 2) + offset_x
            
            if vertical_position == "top":
                y = geom.y + screen_margin + offset_y
            else:  
                y = geom.y + geom.height - self.HEIGHT - screen_margin + offset_y
            
            x = max(geom.x, min(int(x), geom.x + geom.width - self.WIDTH))
            y = max(geom.y, min(int(y), geom.y + geom.height - self.HEIGHT))
            
            self.window.move(x, y)
            self.window.present()
            self.search_entry.grab_focus()
            
        except Exception as e:
            print(f"DEBUG: Position error: {e}")
            self.window.present()
            self.search_entry.grab_focus()
        
        return False

    def run(self):
        def signal_handler(sig, frame):
            self.quit()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            self.window.show_all()
            Gtk.main()
        except KeyboardInterrupt:
            self.quit()
        except Exception as e:
            print(f"DEBUG: Run error: {e}")
            self.quit()

if __name__ == "__main__":
    TMenu().run()
