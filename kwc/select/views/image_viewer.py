"""
Main image viewer component.

This module contains the main image display area with crossfade transitions.
"""

from pathlib import Path
from typing import Optional

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio

from ..utils.constants import CROSSFADE_DURATION


class ImageViewer:
    """Main image display widget with crossfade transitions."""

    def __init__(self):
        """Initialize the image viewer."""
        self.widget = self._create_image_stack()
        self._current_picture = self._picture_a

    def _create_image_stack(self) -> Gtk.Stack:
        """Create the image stack for crossfade animations."""
        self.picture_stack = Gtk.Stack()
        self.picture_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.picture_stack.set_transition_duration(CROSSFADE_DURATION)
        
        # Create two picture widgets for crossfading
        self._picture_a = Gtk.Picture()
        self._picture_b = Gtk.Picture()
        
        # Configure layout and alignment
        self.picture_stack.set_hexpand(False)
        self.picture_stack.set_halign(Gtk.Align.CENTER)
        self.picture_stack.set_valign(Gtk.Align.CENTER)
        self.picture_stack.set_vexpand(True)
        
        for picture in [self._picture_a, self._picture_b]:
            picture.set_hexpand(False)
            picture.set_halign(Gtk.Align.CENTER)
        
        self.picture_stack.add_child(self._picture_a)
        self.picture_stack.add_child(self._picture_b)
        
        # Add styling
        self.picture_stack.set_margin_top(16)
        self.picture_stack.set_margin_bottom(16)
        self.picture_stack.add_css_class("main-image-stack")
        
        return self.picture_stack

    def display_image(self, image_path: Path) -> bool:
        """
        Display an image with crossfade transition.
        
        Args:
            image_path: Path to the image to display
            
        Returns:
            True if successful, False otherwise
        """
        if not image_path.exists():
            return False
            
        try:
            file = Gio.File.new_for_path(str(image_path))
            
            # Use the non-current picture for the new image
            if self._current_picture == self._picture_a:
                self._picture_b.set_file(file)
                self.picture_stack.set_visible_child(self._picture_b)
                self._current_picture = self._picture_b
            else:
                self._picture_a.set_file(file)
                self.picture_stack.set_visible_child(self._picture_a)
                self._current_picture = self._picture_a
                
            return True
            
        except Exception as e:
            print(f"Error displaying image {image_path}: {e}")
            return False

    def clear_image(self) -> None:
        """Clear the currently displayed image."""
        self._picture_a.set_file(None)
        self._picture_b.set_file(None)
