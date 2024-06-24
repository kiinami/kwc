import os
from pathlib import Path

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk


class MyWindow(Gtk.ApplicationWindow):
    def __init__(self, dir: Path, selected_dir: Path, discarded_dir: Path, **kwargs):
        super().__init__(**kwargs, title='KWC Selector')
        self.dir = dir
        self.selected_dir = selected_dir
        self.discarded_dir = discarded_dir

        self.dirlist = sorted(list(dir.glob('*.jpg')), key=lambda x: int(x.stem), reverse=True)

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
        self.new_picture()

    def on_key_press_event(self, keyval, keycode, *args):
        if keycode == ord('q'):
            self.on_keep()
        elif keycode == ord('w'):
            self.on_discard()
        return False

    def new_picture(self):
        if not self.dirlist:
            self.close()
        path = self.dirlist.pop()
        self.picture.set_filename(str(path))
        self.picture_path = path

    def on_keep(self):
        os.rename(self.picture_path, self.selected_dir / self.picture_path.name)
        self.new_picture()

    def on_discard(self):
        os.rename(self.picture_path, self.discarded_dir / self.picture_path.name)
        self.new_picture()


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
