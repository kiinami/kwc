from gi.repository import Gtk, Gio

THUMBNAIL_WIDTH = 160
THUMBNAIL_HEIGHT = 100

class LazyThumbnailButton(Gtk.Button):
    """A button that lazy-loads thumbnail images for performance."""
    def __init__(self, image_path, index, parent_window):
        super().__init__()
        self.image_path = image_path
        self.index = index
        self.parent_window = parent_window
        self.is_loaded = False
        self.picture = None
        self._create_placeholder()
        self.set_size_request(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)

    def _create_placeholder(self):
        placeholder = Gtk.Box()
        placeholder.set_size_request(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)
        placeholder.add_css_class("thumbnail-placeholder")
        self.set_child(placeholder)

    def load_thumbnail(self):
        if not self.is_loaded:
            file = Gio.File.new_for_path(str(self.image_path))
            self.picture = Gtk.Picture.new_for_file(file)
            self.picture.set_size_request(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)
            self.set_child(self.picture)
            self.is_loaded = True

    def update_image_path(self, new_path):
        self.image_path = new_path
        if self.is_loaded:
            self.is_loaded = False
            self.load_thumbnail()

class GroupThumbnailButton(Gtk.Button):
    """A button representing a group of similar images as a stack with badge."""
    def __init__(self, group, group_idx, parent_window):
        super().__init__()
        self.group = group
        self.group_idx = group_idx
        self.parent_window = parent_window
        self.is_loaded = False
        self.stack_overlay = None
        self._create_stack_placeholder()
        self.set_size_request(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)

    def _create_stack_placeholder(self):
        overlay = Gtk.Overlay()
        self.picture = Gtk.Picture()
        self.picture.set_size_request(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)
        overlay.set_child(self.picture)
        for i in range(1, min(4, len(self.group))):
            border = Gtk.Box()
            border.set_size_request(THUMBNAIL_WIDTH - i*8, THUMBNAIL_HEIGHT - i*5)
            border.add_css_class(f"group-stack-border-{i}")
            overlay.add_overlay(border)
        if len(self.group) > 1:
            badge = Gtk.Label(label=str(len(self.group)))
            badge.add_css_class("group-badge")
            badge.set_halign(Gtk.Align.END)
            badge.set_valign(Gtk.Align.START)
            overlay.add_overlay(badge)
        self.set_child(overlay)
        self.stack_overlay = overlay

    def load_thumbnail(self):
        if not self.is_loaded and self.group:
            file = Gio.File.new_for_path(str(self.group[0]))
            self.picture.set_file(file)
            self.is_loaded = True

    def update_group(self, new_group):
        self.group = new_group
        self.is_loaded = False
        self._create_stack_placeholder()
        self.load_thumbnail()
