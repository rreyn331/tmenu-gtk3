import os
import sys
import subprocess
import shlex
import shutil
import signal
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib,GdkPixbuf

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
        display = Gdk.Display.get_default()
        self.is_wayland = 'Wayland' in type(display).__name__
        self.display_type = "wayland" if self.is_wayland else "x11"
        
        self.icon_theme = Gtk.IconTheme.get_default()
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
        self.window.set_size_request(self.WIDTH, self.HEIGHT)
        self.window.set_position(Gtk.WindowPosition.NONE)
        
        self.active_list = None
        self.build_ui()
        
        # DAEMON EVENTS: Force auto-hiding logic
        self.window.connect("focus-out-event", self.on_focus_out)
        self.window.connect("delete-event", lambda w, e: self.hide_menu())
        self.window.connect("key-press-event", self.on_key)
        self.window.connect("button-press-event", self.on_window_click)
        self.window.connect("map-event", self.on_window_mapped)

    # --- DAEMON & VISIBILITY METHODS ---
    def show_menu(self, *args):
        self.set_smart_position()
        self.window.show_all()
        
        # Bypass Window Manager focus stealing prevention
        self.window.present_with_time(Gdk.CURRENT_TIME)
        
        # Wait a tiny fraction of a second to guarantee the WM gives us focus, 
        # otherwise clicking off the menu won't work because it never "had" focus!
        GLib.timeout_add(50, self.force_focus)
        
        return True

    def force_focus(self):
        """Helper to aggressively steal keyboard focus after mapping"""
        self.window.grab_focus()
        self.search_entry.grab_focus()
        return False

    def on_focus_out(self, widget, event):
        """Triggered when the user clicks somewhere else on the screen"""
        self.hide_menu()
        return False

    def hide_menu(self, *args):
        # Prevent double-hiding recursive loops
        if not self.window.get_visible():
            return False
            
        self.window.hide()
        self.search_entry.set_text("") # Clear search automatically
        
        # If the daemon isn't managing this window, kill the process completely so it doesn't hang!
        if getattr(self, "is_daemon", False) == False:
            self.true_quit()
            
        return False

    def true_quit(self, *args):
        """Used to actually kill the program when needed"""
        try:
            Gtk.main_quit()
        except:
            pass
        sys.exit(0)
    # ------------------------------------

    def on_window_click(self, widget, event):
        return False

    def on_window_mapped(self, widget, event):
        if not self.positioned:
            self.positioned = True
            GLib.timeout_add(50, self.set_smart_position)
        return False

    def get_scaled_icon(self, name, size):
        """
        Handles:
        1. Absolute paths
        2. Files in /usr/share/pixmaps/ (checking common extensions)
        3. Theme lookups with common search paths
        """
        if not name:
            return self._get_fallback_icon(size)

        # 1. Handle Absolute Paths directly
        if name.startswith("/") and os.path.exists(name):
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(name, size, size, True)
                return Gtk.Image.new_from_pixbuf(pb)
            except Exception:
                pass

        # 2. Broader /usr/share/pixmaps/ check
        # Some .desktop files say "icon" but the file is "icon.png" or "icon.xpm"
        base_pixmap = os.path.join("/usr/share/pixmaps", name)
        # Try original name, then try adding common extensions if they aren't there
        exts_to_try = ["", ".png", ".svg", ".xpm", ".jpg"]
        for ext in exts_to_try:
            test_path = base_pixmap + ext
            if os.path.exists(test_path) and not os.path.isdir(test_path):
                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(test_path, size, size, True)
                    return Gtk.Image.new_from_pixbuf(pb)
                except Exception:
                    continue

        # 3. Enhanced Theme Lookup
        # We strip the extension because GTK Icon Theme prefers 'gimp' over 'gimp.png'
        clean_name = os.path.splitext(os.path.basename(name))[0]
        
        # Check theme for the cleaned name
        if self.icon_theme.has_icon(clean_name):
            img = Gtk.Image.new_from_icon_name(clean_name, Gtk.IconSize.MENU)
            img.set_pixel_size(size)
            return img

        # Final attempt: search the theme for the raw name
        if self.icon_theme.has_icon(name):
            img = Gtk.Image.new_from_icon_name(name, Gtk.IconSize.MENU)
            img.set_pixel_size(size)
            return img

        return self._get_fallback_icon(size)

    def _get_fallback_icon(self, size):
        """Standard fallback that isn't a terminal if possible"""
        # 'system-run' or 'gear' is often less confusing than a terminal icon
        fallback = "application-x-executable" 
        img = Gtk.Image.new_from_icon_name(fallback, Gtk.IconSize.MENU)
        img.set_pixel_size(size)
        return img

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
        
        # FIX: The proper way to handle mouse clicks on a ListBox
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

    def on_app_clicked(self, listbox, row):
        """Triggered when an app row is clicked with the mouse"""
        if row and hasattr(row, 'app_data'):
            self.launch_item(row.app_data)

    def create_app_row(self, app, visible=True):
        row = Gtk.ListBoxRow()
        row.app_data = app
        box = Gtk.Box(spacing=10, border_width=5)
        
        # Pull icon name/path from various possible keys
        icon_name = app.get("Icon") or app.get("icon") or "application-x-executable"
        
        icon_widget = self.get_scaled_icon(icon_name, self.ICON_SIZE)
        box.pack_start(icon_widget, False, False, 0)
        
        row.label_widget = Gtk.Label(label=str(app.get("Name") or "Unknown"), xalign=0)
        box.pack_start(row.label_widget, True, True, 0)
        
        row.add(box)
        self.app_list.add(row)
        
        if visible:
            row.show_all()
        else:
            row.hide()
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
        
        # SPEED OPTIMIZATION 2: Prevent GTK from redrawing widgets that are already visible
        for row in self.app_list.get_children():
            if row == self.terminal_row: 
                if row.get_visible(): row.hide()
                continue
            
            name = row.app_data.get("Name")
            should_show = (name in match_names or name in p_matches)
            
            if should_show:
                if not row.get_visible(): row.show_all()
                found = True
            else:
                if row.get_visible(): row.hide()

        base_cmd = txt.split()[0] if txt else ""
        if not found and base_cmd and shutil.which(base_cmd):
            if not self.terminal_row.get_visible(): self.terminal_row.show_all()
            self.terminal_row.app_data["Exec"] = txt 
            self.terminal_row.label_widget.set_text(f"Run: {txt}")
        else:
            if self.terminal_row.get_visible(): self.terminal_row.hide()

        self.select_first_visible(self.app_list)

    def launch_item(self, data):
        if data.get("is_power"):
            act = data.get("action")
            if hasattr(power, act): 
                try: 
                    getattr(power, act)()
                except Exception: 
                    pass

        elif data.get("is_terminal"):
            cmd = data.get("Exec", "")
            try: 
                subprocess.Popen(
                    ["x-terminal-emulator", "-e", f"bash -c {shlex.quote(cmd + '; exec bash')}"], 
                    start_new_session=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except Exception: 
                pass

        else:
            cmd = data.get("Exec", "")
            args = [a for a in shlex.split(cmd) if not a.startswith('%')]
            try:
                # FIX: Send all background app logs to DEVNULL so they don't hang 
                # looking for the closed terminal window!
                subprocess.Popen(
                    args, 
                    start_new_session=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except Exception: 
                pass
        
        # DAEMON ACTION: Hide the menu so it is ready for next time
        self.hide_menu()

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
        
        # SPEED OPTIMIZATION 3: Prevent Category Redraws
        for child in self.app_list.get_children():
            if child == self.terminal_row: 
                if child.get_visible(): child.hide()
                continue
                
            is_match = target == "All Applications" or child.app_data.get("Categories") == target
            should_show = (is_match and not child.app_data.get("is_power"))
            
            if should_show:
                if not child.get_visible(): child.show_all()
            else:
                if child.get_visible(): child.hide()

    def select_first_visible(self, listbox):
        for r in listbox.get_children():
            if r.get_visible():
                listbox.select_row(r)
                break

    def on_key(self, w, e):
        k = e.keyval
        if k == Gdk.KEY_Escape: 
            self.hide_menu() # Hides gracefully
            return True
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
            
            if not monitor: return False
            
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
            
        except Exception as e:
            print(f"DEBUG: Position error: {e}")
        
        return False

    def run(self):
        # Fallback runner if the user launches normally without the daemon
        def signal_handler(sig, frame):
            self.true_quit()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            self.show_menu()
            Gtk.main()
        except KeyboardInterrupt:
            self.true_quit()
        except Exception as e:
            print(f"DEBUG: Run error: {e}")
            self.true_quit()

if __name__ == "__main__":
    TMenu().run()
