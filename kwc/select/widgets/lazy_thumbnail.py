"""
Lazy-loading thumbnail button widget.

This module contains a button widget that loads thumbnail images
on demand for better performance.
"""

from pathlib import Path
from typing import Optional, Callable

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio

from ..utils.constants import THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT


class LazyThumbnailButton(Gtk.Button):
    """A button that lazy-loads thumbnail images for performance."""
    
    def __init__(self, image_path: Path, index: int, on_clicked: Optional[Callable[[int], None]] = None):
        """
        Initialize the thumbnail button.
        
        Args:
            image_path: Path to the image file
            index: Index of this image in the collection
            on_clicked: Callback for when button is clicked
        """
        super().__init__()
        
        self.image_path = image_path
        self.index = index
        self._on_clicked_callback = on_clicked
        self._is_loaded = False
        self._picture: Optional[Gtk.Picture] = None
        
        self._create_placeholder()
        self.set_size_request(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)
        
        if on_clicked:
            self.connect('clicked', self._on_button_clicked)

    def _create_placeholder(self) -> None:
        """Create a placeholder widget for the thumbnail."""
        placeholder = Gtk.Box()
        placeholder.set_size_request(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)
        placeholder.add_css_class("thumbnail-placeholder")
        self.set_child(placeholder)

    def _on_button_clicked(self, button: Gtk.Button) -> None:
        """Handle button click events."""
        if self._on_clicked_callback:
            self._on_clicked_callback(self.index)

    def load_thumbnail(self) -> None:
        """Load the thumbnail image if not already loaded."""
        if self._is_loaded:
            return
            
        try:
            file = Gio.File.new_for_path(str(self.image_path))
            self._picture = Gtk.Picture.new_for_file(file)
            self._picture.set_size_request(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)
            self.set_child(self._picture)
            self._is_loaded = True
        except Exception as e:
            print(f"Error loading thumbnail for {self.image_path}: {e}")

    def update_image_path(self, new_path: Path) -> None:
        """
        Update the image path and reload the thumbnail if needed.
        
        Args:
            new_path: New path to the image file
        """
        self.image_path = new_path
        if self._is_loaded:
            self._is_loaded = False
            self.load_thumbnail()

    @property
    def is_loaded(self) -> bool:
        """Check if the thumbnail has been loaded."""
        return self._is_loaded
