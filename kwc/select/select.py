import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GObject, Gio

import os
from pathlib import Path


# Load CSS for thumbnail coloring
css_provider = Gtk.CssProvider()
css_provider.load_from_path(str(Path(__file__).parent / "style.css"))
Gtk.StyleContext.add_provider_for_display(
    Gdk.Display.get_default(),
    css_provider,
    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
)


class ThumbnailItem(GObject.GObject):
    def __init__(self, filepath):
        super().__init__()
        self.filepath = filepath


class MyWindow(Gtk.ApplicationWindow):
    def __init__(self, dir: Path, selected_dir: Path, discarded_dir: Path, **kwargs):
        super().__init__(**kwargs, title='KWC Selector')
        self.dir = dir
        self.selected_dir = selected_dir
        self.discarded_dir = discarded_dir

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)
        self.set_child(box)

        # Picture stack for crossfade animation
        self.picture_stack = Gtk.Stack()
        self.picture_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.picture_stack.set_transition_duration(200)  # 200ms crossfade

        self.picture_a = Gtk.Picture()
        self.picture_b = Gtk.Picture()
        self.picture_stack.add_child(self.picture_a)
        self.picture_stack.add_child(self.picture_b)
        self.current_picture = self.picture_a  # Track which picture is currently visible

        box.append(self.picture_stack)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.keep_button = Gtk.Button.new_with_label('Keep (q)')
        self.keep_button.connect('clicked', lambda _: self.on_keep())
        hbox.append(self.keep_button)
        self.discard_button = Gtk.Button.new_with_label('Discard (w)')
        self.discard_button.connect('clicked', lambda _: self.on_discard())
        hbox.append(self.discard_button)
        hbox.set_halign(Gtk.Align.CENTER)
        box.append(hbox)

        keycont = Gtk.EventControllerKey()
        keycont.connect('key-pressed', self.on_key_press_event)
        self.add_controller(keycont)

        # --- Filmstrip using HBox for perfect centering ---
        self.filmstrip_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.filmstrip_box.set_valign(Gtk.Align.CENTER)
        self.filmstrip_scroller = Gtk.ScrolledWindow()
        self.filmstrip_scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.filmstrip_scroller.set_child(self.filmstrip_box)
        self.filmstrip_scroller.set_min_content_height(100)
        box.append(self.filmstrip_scroller)

        # Set up images and initial selection
        self.all_images = self.get_all_images()
        self.current_index = 0
        self.populate_filmstrip()
        self.set_initial_selection()

    def get_all_images(self):
        # Collect all jpgs from dir, selected_dir, and discarded_dir
        images = list(self.dir.glob('*.jpg'))
        images += list(self.selected_dir.glob('*.jpg'))
        images += list(self.discarded_dir.glob('*.jpg'))
        images = sorted(images, key=lambda x: int(x.stem.split('_')[-1]))
        return images

    def populate_filmstrip(self):
        # Remove all children
        child = self.filmstrip_box.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self.filmstrip_box.remove(child)
            child = next_child
        # Add all images as buttons
        self.thumb_buttons = []
        for idx, img in enumerate(self.all_images):
            file = Gio.File.new_for_path(str(img))
            pic = Gtk.Picture.new_for_file(file)
            pic.set_size_request(160, 100)
            button = Gtk.Button()
            button.set_child(pic)
            button.connect('clicked', self.on_thumbnail_clicked, idx)
            # Style
            if img.parent == self.selected_dir:
                button.set_css_classes(["thumb-selected"])
            elif img.parent == self.discarded_dir:
                button.set_css_classes(["thumb-discarded"])
            self.filmstrip_box.append(button)
            self.thumb_buttons.append(button)

    def on_thumbnail_clicked(self, button, idx):
        self.current_index = idx
        self.update_main_image(idx)
        self.center_filmstrip_on_selected(idx)

    def set_initial_selection(self):
        for i, img in enumerate(self.all_images):
            if Path(img).parent == self.dir:
                self.current_index = i
                self.update_main_image(i)
                GObject.idle_add(self.center_filmstrip_on_selected, i)
                return
        self.current_index = 0
        self.update_main_image(0)
        GObject.idle_add(self.center_filmstrip_on_selected, 0)

    def center_filmstrip_on_selected(self, idx):
        # Smoothly animate to center the selected thumbnail
        if 0 <= idx < len(self.thumb_buttons):
            button = self.thumb_buttons[idx]
            alloc = button.get_allocation()
            scroll = self.filmstrip_scroller
            hadj = scroll.get_hadjustment()
            if hadj:
                visible_width = hadj.get_page_size() or scroll.get_allocation().width or 1
                target_x = alloc.x + alloc.width // 2 - visible_width // 2
                target_x = max(0, min(target_x, hadj.get_upper() - visible_width))

                # Animate the scroll position
                self.animate_scroll_to(hadj, target_x)
        return False

    def animate_scroll_to(self, adjustment, target_value):
        # Smooth scrolling animation
        start_value = adjustment.get_value()
        diff = target_value - start_value

        if abs(diff) < 1:  # Already close enough
            adjustment.set_value(target_value)
            return

        duration = 300  # milliseconds
        steps = 30
        step_time = duration // steps
        step_size = diff / steps

        step_count = [0]  # Use list to make it mutable in closure

        def animate_step():
            step_count[0] += 1
            progress = step_count[0] / steps

            # Easing function (ease-out)
            eased_progress = 1 - (1 - progress) ** 3

            current_value = start_value + diff * eased_progress
            adjustment.set_value(current_value)

            if step_count[0] >= steps:
                adjustment.set_value(target_value)
                return False  # Stop the timer
            return True  # Continue the timer

        GObject.timeout_add(step_time, animate_step)

    def update_main_image(self, idx):
        path = self.all_images[idx]

        # Animate the main image transition
        self.animate_image_transition(path)

        # Update button color
        for i, btn in enumerate(self.thumb_buttons):
            btn.set_css_classes([])
            if self.all_images[i].parent == self.selected_dir:
                btn.set_css_classes(["thumb-selected"])
            elif self.all_images[i].parent == self.discarded_dir:
                btn.set_css_classes(["thumb-discarded"])
            if i == idx:
                btn.set_css_classes(btn.get_css_classes() + ["current-thumb"])

        if path.parent == self.selected_dir:
            self.keep_button.set_css_classes(["thumb-selected"])
            self.discard_button.set_css_classes([])
        elif path.parent == self.discarded_dir:
            self.keep_button.set_css_classes([])
            self.discard_button.set_css_classes(["thumb-discarded"])
        else:
            self.keep_button.set_css_classes([])
            self.discard_button.set_css_classes([])
        self.current_index = idx
        self.picture_path = path

    def animate_image_transition(self, new_image_path):
        # Use the non-visible picture for the new image
        if self.current_picture == self.picture_a:
            next_picture = self.picture_b
            self.current_picture = self.picture_b
        else:
            next_picture = self.picture_a
            self.current_picture = self.picture_a

        # Load new image into the hidden picture
        next_picture.set_filename(str(new_image_path))

        # Crossfade to the new picture
        self.picture_stack.set_visible_child(next_picture)

    def on_key_press_event(self, keyval, keycode, *args):
        if keyval == Gdk.KEY_Left:
            if self.current_index > 0:
                self.current_index -= 1
                self.update_main_image(self.current_index)
                self.center_filmstrip_on_selected(self.current_index)
            return True
        elif keyval == Gdk.KEY_Right:
            if self.current_index < len(self.all_images) - 1:
                self.current_index += 1
                self.update_main_image(self.current_index)
                self.center_filmstrip_on_selected(self.current_index)
            return True
        if keycode == ord('q'):
            self.on_keep()
        elif keycode == ord('w'):
            self.on_discard()
        return False

    def on_keep(self):
        dest = self.selected_dir / self.picture_path.name
        if self.picture_path.parent != self.selected_dir:
            os.rename(self.picture_path, dest)
            self.all_images[self.current_index] = dest
            self.populate_filmstrip()
            self.update_main_image(self.current_index)
            GObject.idle_add(self.center_filmstrip_on_selected, self.current_index)
        else:
            self.update_main_image(self.current_index)

    def on_discard(self):
        dest = self.discarded_dir / self.picture_path.name
        if self.picture_path.parent != self.discarded_dir:
            os.rename(self.picture_path, dest)
            self.all_images[self.current_index] = dest
            self.populate_filmstrip()
            self.update_main_image(self.current_index)
            GObject.idle_add(self.center_filmstrip_on_selected, self.current_index)
        else:
            self.update_main_image(self.current_index)


def on_activate(app, dir: Path, selected_dir: Path, discarded_dir: Path):
    win = MyWindow(dir, selected_dir, discarded_dir, application=app)
    win.present()


def select(dir: Path, selected_dir: Path, discarded_dir: Path):
    if not selected_dir.exists():
        selected_dir.mkdir()
    if not discarded_dir.exists():
        discarded_dir.mkdir()
    app = Gtk.Application(application_id='com.kwc.Selector')
    app.connect('activate', on_activate, dir, selected_dir, discarded_dir)
    app.run(None)
