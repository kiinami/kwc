"""
Action bar view component.

This module contains the action bar with Keep/Discard buttons for the image selector.
"""

from pathlib import Path
from typing import Callable, Optional

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk


class ActionBarView:
    """Action bar with Keep/Discard buttons for image selector."""

    def __init__(self, on_keep: Optional[Callable[[], None]] = None, 
                 on_discard: Optional[Callable[[], None]] = None,
                 on_key_press: Optional[Callable] = None):
        """
        Initialize the action bar.
        
        Args:
            on_keep: Callback for keep button clicks
            on_discard: Callback for discard button clicks  
            on_key_press: Callback for key press events
        """
        self._on_keep_callback = on_keep
        self._on_discard_callback = on_discard
        self._on_key_press_callback = on_key_press
        
        self.widget = self._create_action_buttons()

    def _create_action_buttons(self) -> Gtk.Box:
        """Create the Keep/Discard action buttons (Adwaita style)."""
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        hbox.set_halign(Gtk.Align.CENTER)
        
        # Keep button
        self.keep_button = Gtk.Button.new_with_label('Keep (q)')
        self.keep_button.add_css_class("suggested-action")
        self.keep_button.connect('clicked', lambda _: self._on_keep_clicked())
        
        if self._on_key_press_callback:
            keycont_keep = Gtk.EventControllerKey()
            keycont_keep.connect('key-pressed', self._on_key_press_callback)
            self.keep_button.add_controller(keycont_keep)
        
        hbox.append(self.keep_button)
        
        # Discard button
        self.discard_button = Gtk.Button.new_with_label('Discard (w)')
        self.discard_button.add_css_class("destructive-action")
        self.discard_button.connect('clicked', lambda _: self._on_discard_clicked())
        
        if self._on_key_press_callback:
            keycont_discard = Gtk.EventControllerKey()
            keycont_discard.connect('key-pressed', self._on_key_press_callback)
            self.discard_button.add_controller(keycont_discard)
        
        hbox.append(self.discard_button)
        
        return hbox

    def _on_keep_clicked(self) -> None:
        """Handle keep button clicks."""
        if self._on_keep_callback:
            self._on_keep_callback()

    def _on_discard_clicked(self) -> None:
        """Handle discard button clicks."""
        if self._on_discard_callback:
            self._on_discard_callback()

    def update_button_states(self, image_path: Path, selected_dir: Path, discarded_dir: Path) -> None:
        """
        Update action button states based on current image location.
        
        Args:
            image_path: Path to the current image
            selected_dir: Path to selected images directory
            discarded_dir: Path to discarded images directory
        """
        if image_path.parent == selected_dir:
            self.keep_button.set_sensitive(False)
            self.discard_button.set_sensitive(True)
        elif image_path.parent == discarded_dir:
            self.keep_button.set_sensitive(True)
            self.discard_button.set_sensitive(False)
        else:
            self.keep_button.set_sensitive(True)
            self.discard_button.set_sensitive(True)
