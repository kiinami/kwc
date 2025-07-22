# Standard library imports
from pathlib import Path

# Third-party imports
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk


class ActionBar:
    """Action bar with Keep/Discard buttons for image selector."""

    def __init__(self, parent_window):
        self.parent_window = parent_window
        self.widget = self._create_action_buttons()

    def _create_action_buttons(self) -> Gtk.Box:
        """Create the Keep/Discard action buttons (Adwaita style)."""
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.keep_button = Gtk.Button.new_with_label('Keep (q)')
        self.keep_button.add_css_class("suggested-action")
        self.keep_button.connect('clicked', lambda _: self.on_keep())
        keycont_keep = Gtk.EventControllerKey()
        keycont_keep.connect('key-pressed', self.parent_window.on_key_press_event)
        self.keep_button.add_controller(keycont_keep)
        hbox.append(self.keep_button)
        
        self.discard_button = Gtk.Button.new_with_label('Discard (w)')
        self.discard_button.add_css_class("destructive-action")
        self.discard_button.connect('clicked', lambda _: self.on_discard())
        keycont_discard = Gtk.EventControllerKey()
        keycont_discard.connect('key-pressed', self.parent_window.on_key_press_event)
        self.discard_button.add_controller(keycont_discard)
        hbox.append(self.discard_button)
        
        hbox.set_halign(Gtk.Align.CENTER)
        return hbox

    def update_button_states(self, image_path: Path, selected_dir: Path, discarded_dir: Path):
        """Update action button states based on current image location."""
        if image_path.parent == selected_dir:
            self.keep_button.set_sensitive(False)
            self.discard_button.set_sensitive(True)
        elif image_path.parent == discarded_dir:
            self.keep_button.set_sensitive(True)
            self.discard_button.set_sensitive(False)
        else:
            self.keep_button.set_sensitive(True)
            self.discard_button.set_sensitive(True)

    def on_keep(self):
        """Handle keep button click."""
        if self.parent_window.picture_path.parent != self.parent_window.selected_dir:
            self.parent_window._move_image_to_directory(self.parent_window.selected_dir)
            next_idx = self.parent_window._find_next_unclassified_index()
            if next_idx is not None:
                self.parent_window._navigate_to_image(next_idx)

    def on_discard(self):
        """Handle discard button click."""
        if self.parent_window.picture_path.parent != self.parent_window.discarded_dir:
            self.parent_window._move_image_to_directory(self.parent_window.discarded_dir)
            next_idx = self.parent_window._find_next_unclassified_index()
            if next_idx is not None:
                self.parent_window._navigate_to_image(next_idx)
