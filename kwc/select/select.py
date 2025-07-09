import os
from pathlib import Path

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk

# Load CSS for thumbnail coloring
css_provider = Gtk.CssProvider()
css_provider.load_from_path(str(Path(__file__).parent / "style.css"))
Gtk.StyleContext.add_provider_for_display(
    Gdk.Display.get_default(),
    css_provider,
    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
)


class MyWindow(Gtk.ApplicationWindow):
    def __init__(self, dir: Path, selected_dir: Path, discarded_dir: Path, **kwargs):
        super().__init__(**kwargs, title='KWC Selector')
        self.dir = dir
        self.selected_dir = selected_dir
        self.discarded_dir = discarded_dir

        self.dirlist = sorted(list(dir.glob('*.jpg')), key=lambda x: int(x.stem.split("_")[-1]), reverse=True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)
        self.set_child(box)

        self.picture = Gtk.Picture()
        box.append(self.picture)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        keep_button = Gtk.Button.new_with_label('Keep (q)')
        keep_button.connect('clicked', lambda _: self.on_keep())
        hbox.append(keep_button)
        discard_button = Gtk.Button.new_with_label('Discard (w)')
        discard_button.connect('clicked', lambda _: self.on_discard())
        hbox.append(discard_button)
        hbox.set_halign(Gtk.Align.CENTER)
        box.append(hbox)

        keycont = Gtk.EventControllerKey()
        keycont.connect('key-pressed', self.on_key_press_event)
        self.add_controller(keycont)

        self.picture_path = None
        self.processed = []  # Store processed images (Path, action)

        # Unified thumbnail row: previous, current, next (now using HBox, not scrollable)
        self.thumb_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.thumb_row.set_valign(Gtk.Align.CENTER)
        box.append(self.thumb_row)

        # Gather all images from dir, selected_dir, and discarded_dir
        self.visible_thumb_window = 13  # Odd number for true centering
        self.all_images = self.get_all_images()
        # Set current_index to the first image in the given directory (not selected/discarded)
        first_image = None
        for i, img in enumerate(self.all_images):
            if img.parent == self.dir:
                first_image = i
                break
        self.current_index = first_image if first_image is not None else 0
        self.new_picture()

    def on_key_press_event(self, keyval, keycode, *args):
        # Left/right arrow navigation
        if keyval == Gdk.KEY_Left:
            if self.current_index > 0:
                self.current_index -= 1
                self.new_picture()
            return True
        elif keyval == Gdk.KEY_Right:
            if self.current_index < len(self.all_images) - 1:
                self.current_index += 1
                self.new_picture()
            return True
        # q/w for keep/discard
        if keycode == ord('q'):
            self.on_keep()
        elif keycode == ord('w'):
            self.on_discard()
        return False

    def on_thumbnail_clicked(self, button, idx, *args):
        self.current_index = idx
        self.new_picture()

    def get_image_status(self, path):
        if path.parent == self.selected_dir:
            return 'selected'
        elif path.parent == self.discarded_dir:
            return 'discarded'
        else:
            return 'unprocessed'

    def get_all_images(self):
        # Collect all jpgs from dir, selected_dir, and discarded_dir
        images = list(self.dir.glob('*.jpg'))
        images += list(self.selected_dir.glob('*.jpg'))
        images += list(self.discarded_dir.glob('*.jpg'))
        # Sort as before
        images = sorted(images, key=lambda x: int(x.stem.split("_")[-1]))
        return images

    def new_picture(self):
        if not self.all_images:
            self.close()
        self.picture_path = self.all_images[self.current_index]
        self.picture.set_filename(str(self.picture_path))
        self.update_thumbnails()
        # No need to center carousel, as it is not scrollable

    def center_carousel_on_current(self):
        # No-op: not needed when not scrollable
        pass

    def on_keep(self):
        # Allow changing selection: move from discarded to selected, or from selected to selected
        dest = self.selected_dir / self.picture_path.name
        if self.picture_path.parent != self.selected_dir:
            os.rename(self.picture_path, dest)
            self.all_images = self.get_all_images()
            self.current_index = self.all_images.index(dest)
        self.new_picture()

    def on_discard(self):
        # Allow changing selection: move from selected to discarded, or from discarded to discarded
        dest = self.discarded_dir / self.picture_path.name
        if self.picture_path.parent != self.discarded_dir:
            os.rename(self.picture_path, dest)
            self.all_images = self.get_all_images()
            self.current_index = self.all_images.index(dest)
        self.new_picture()

    def update_thumbnails(self):
        # Remove all children from the thumbnail row (HBox)
        child = self.thumb_row.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self.thumb_row.remove(child)
            child = next_child

        half = self.visible_thumb_window // 2
        start = max(0, self.current_index - half)
        end = min(len(self.all_images), self.current_index + half + 1)
        pad_left = half - self.current_index if self.current_index - half < 0 else 0
        pad_right = (self.current_index + half + 1) - len(self.all_images) if self.current_index + half + 1 > len(self.all_images) else 0
        for _ in range(pad_left):
            self.thumb_row.append(Gtk.Box())
        for idx in range(start, end):
            path = self.all_images[idx]
            pic = Gtk.Picture()
            pic.set_filename(str(path))
            pic.set_size_request(100, 66)
            status = self.get_image_status(path)
            button = Gtk.Button()
            button.set_child(pic)
            if status == 'selected':
                button.set_css_classes(["thumb-selected"])
            elif status == 'discarded':
                button.set_css_classes(["thumb-discarded"])
            if idx == self.current_index:
                frame = Gtk.Frame()
                frame.set_child(button)
                frame.set_css_classes(["current-thumb"])
                self.thumb_row.append(frame)
            else:
                self.thumb_row.append(button)
            button.connect('clicked', self.on_thumbnail_clicked, idx)
        for _ in range(pad_right):
            self.thumb_row.append(Gtk.Box())


def on_activate(app, dir: Path, selected_dir: Path, discarded_dir: Path):
    # Create window
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
