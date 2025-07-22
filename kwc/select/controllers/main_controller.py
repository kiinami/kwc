"""
Main controller for the KWC Selector application.

This module handles the coordination between models and views,
managing user interactions and application state.
"""

from pathlib import Path
from typing import Optional

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gdk

from ..models.image_manager import ImageManager
from ..views.action_bar import ActionBarView
from ..views.filmstrip import FilmstripView
from ..views.image_viewer import ImageViewer


class MainController:
    """Main controller that coordinates between models and views."""

    def __init__(self, image_manager: ImageManager, action_bar: ActionBarView, 
                 filmstrip: FilmstripView, image_viewer: ImageViewer,
                 on_progress_updated: Optional[callable] = None):
        """
        Initialize the main controller.
        
        Args:
            image_manager: The image manager model
            action_bar: The action bar view
            filmstrip: The filmstrip view
            image_viewer: The image viewer
            on_progress_updated: Callback for progress updates
        """
        self.image_manager = image_manager
        self.action_bar = action_bar
        self.filmstrip = filmstrip
        self.image_viewer = image_viewer
        self._on_progress_updated = on_progress_updated
        
        self._setup_callbacks()
        self._initialize_views()

    def _setup_callbacks(self) -> None:
        """Set up callbacks between components."""
        # Set up image manager callbacks
        self.image_manager.set_image_moved_callback(self._on_image_moved)
        self.image_manager.set_index_changed_callback(self._on_index_changed)

    def _initialize_views(self) -> None:
        """Initialize views with current data."""
        # Populate filmstrip
        self.filmstrip.populate_filmstrip(
            self.image_manager.all_images,
            self.image_manager.selected_dir,
            self.image_manager.discarded_dir
        )
        
        # Set initial selection
        initial_index = self.image_manager.find_initial_selection_index()
        self.navigate_to_image(initial_index)

    def _on_image_moved(self, source_path: Path, dest_path: Path) -> None:
        """Handle image move events from the model."""
        # Update UI state
        current_image = self.image_manager.current_image
        if current_image:
            self.action_bar.update_button_states(
                current_image,
                self.image_manager.selected_dir,
                self.image_manager.discarded_dir
            )
        
        # Update filmstrip styles
        self.filmstrip.update_button_styles(
            self.image_manager.current_index,
            self.image_manager.selected_dir,
            self.image_manager.discarded_dir,
            self.image_manager.all_images
        )
        
        # Notify progress update
        if self._on_progress_updated:
            classified, total = self.image_manager.classification_progress
            self._on_progress_updated(classified, total)

    def _on_index_changed(self, new_index: int) -> None:
        """Handle index change events from the model."""
        current_image = self.image_manager.current_image
        if current_image:
            # Update main image display
            self.image_viewer.display_image(current_image)
            
            # Update action bar states
            self.action_bar.update_button_states(
                current_image,
                self.image_manager.selected_dir,
                self.image_manager.discarded_dir
            )
            
            # Update filmstrip styles and center
            self.filmstrip.update_button_styles(
                new_index,
                self.image_manager.selected_dir,
                self.image_manager.discarded_dir,
                self.image_manager.all_images
            )
            self.filmstrip.center_filmstrip_on_selected(new_index)

    # Navigation methods
    def navigate_to_image(self, index: int) -> bool:
        """Navigate to a specific image index."""
        return self.image_manager.set_current_index(index)

    def navigate_next(self) -> bool:
        """Navigate to the next image."""
        return self.image_manager.navigate_to_next()

    def navigate_previous(self) -> bool:
        """Navigate to the previous image."""
        return self.image_manager.navigate_to_previous()

    # Action methods
    def keep_current_image(self) -> None:
        """Mark current image as selected/kept."""
        if self.image_manager.keep_current_image():
            next_idx = self.image_manager.find_next_unclassified_index()
            if next_idx is not None:
                self.navigate_to_image(next_idx)

    def discard_current_image(self) -> None:
        """Mark current image as discarded."""
        if self.image_manager.discard_current_image():
            next_idx = self.image_manager.find_next_unclassified_index()
            if next_idx is not None:
                self.navigate_to_image(next_idx)

    def undo_last_action(self) -> None:
        """Undo the last image move action."""
        self.image_manager.undo_last_action()

    # Keyboard handling
    def handle_key_press(self, keyval: int, state: Gdk.ModifierType) -> bool:
        """
        Handle keyboard events.
        
        Args:
            keyval: The key value
            state: Modifier state
            
        Returns:
            True if event was handled, False otherwise
        """
        # Keep image (q key)
        if keyval == Gdk.KEY_q:
            self.keep_current_image()
            return True
            
        # Discard image (w key)
        elif keyval == Gdk.KEY_w:
            self.discard_current_image()
            return True
            
        # Undo (Ctrl+Z)
        elif keyval == Gdk.KEY_z and (state & Gdk.ModifierType.CONTROL_MASK):
            self.undo_last_action()
            return True
            
        # Navigate left
        elif keyval == Gdk.KEY_Left:
            self.navigate_previous()
            return True
            
        # Navigate right
        elif keyval == Gdk.KEY_Right:
            self.navigate_next()
            return True
            
        return False
