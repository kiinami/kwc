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
