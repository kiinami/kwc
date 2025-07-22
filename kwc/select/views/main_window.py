"""
Main window for the KWC Selector application.

This module contains the main application window that coordinates all views.
"""

from pathlib import Path
from typing import Optional

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Gdk, Adw

from ..models.image_manager import ImageManager
from ..views.action_bar import ActionBarView
from ..views.filmstrip import FilmstripView
from ..views.image_viewer import ImageViewer
from ..views.dialogs.commit_dialog import CommitDialog
from ..controllers.main_controller import MainController
from ..utils.constants import APPLICATION_TITLE
from ..utils.styling import load_application_css


class MainWindow(Adw.ApplicationWindow):
    """Main window for the KWC Selector application."""

    def __init__(self, application: Adw.Application, source_dir: Path, 
                 selected_dir: Path, discarded_dir: Path, **kwargs):
        """
        Initialize the main window.
        
        Args:
            application: The application instance
            source_dir: Directory containing source images
            selected_dir: Directory for selected/kept images
            discarded_dir: Directory for discarded images
        """
        super().__init__(application=application, title=APPLICATION_TITLE, **kwargs)
        
        # Load CSS styling
        load_application_css()
        
        # Initialize models and views
        self.image_manager = ImageManager(source_dir, selected_dir, discarded_dir)
        
        # Create views
        self.action_bar = ActionBarView(
            on_keep=self._on_keep_clicked,
            on_discard=self._on_discard_clicked,
            on_key_press=self._on_key_press_event
        )
        
        self.filmstrip = FilmstripView(
            on_thumbnail_clicked=self._on_thumbnail_clicked,
            on_scroll_navigation=self._on_scroll_navigation
        )
        
        self.image_viewer = ImageViewer()
        
        # Create controller
        self.controller = MainController(
            image_manager=self.image_manager,
            action_bar=self.action_bar,
            filmstrip=self.filmstrip,
            image_viewer=self.image_viewer,
            on_progress_updated=self._on_progress_updated
        )
        
        # Create commit dialog
        self.commit_dialog = CommitDialog(
            parent_window=self,
            image_manager=self.image_manager,
            on_commit_complete=self._on_commit_complete
        )
        
        # Set up UI
        self._create_header_bar()
        self._create_main_layout()
        self._setup_event_handlers()
        
        # Initialize progress display
        self._update_progress_display()

    def _create_header_bar(self) -> None:
        """Create and configure the header bar."""
        self.header_bar = Adw.HeaderBar()
        self.header_bar.set_show_end_title_buttons(True)
        self.header_bar.set_show_start_title_buttons(True)
        
        # Set title and subtitle
        self.header_bar.set_title_widget(Gtk.Label(label=APPLICATION_TITLE))
        
        # Commit button
        self.commit_button = Gtk.Button.new_with_label("Commit")
        self.commit_button.set_can_focus(True)
        self.commit_button.set_sensitive(True)
        self.commit_button.connect("clicked", self._on_commit_clicked)
        self.header_bar.pack_start(self.commit_button)
        
        # Undo button
        self.undo_button = Gtk.Button()
        icon = Gtk.Image.new_from_icon_name("edit-undo")
        self.undo_button.set_child(icon)
        self.undo_button.set_tooltip_text("Undo (Ctrl+Z)")
        self.undo_button.add_css_class("flat")
        self.undo_button.connect("clicked", lambda _: self.controller.undo_last_action())
        self.header_bar.pack_start(self.undo_button)

    def _create_main_layout(self) -> None:
        """Create the main window layout."""
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(main_vbox)
        
        # Add header bar
        main_vbox.append(self.header_bar)
        
        # Add main image viewer (with expand)
        main_vbox.append(self.image_viewer.widget)
        
        # Add action bar
        main_vbox.append(self.action_bar.widget)
        
        # Add filmstrip
        main_vbox.append(self.filmstrip.widget)

    def _setup_event_handlers(self) -> None:
        """Set up global event handlers."""
        # Keyboard event handler
        key_controller = Gtk.EventControllerKey()
        key_controller.connect('key-pressed', self._on_key_press_event)
        self.add_controller(key_controller)
        
        # Connect filmstrip events
        self.filmstrip.connect_events()

    def _update_progress_display(self) -> None:
        """Update the progress display in the header."""
        classified, total = self.image_manager.classification_progress
        if total == 0:
            percent = 0
        else:
            percent = int((classified / total) * 100)
        
        # Update header subtitle
        title_widget = self.header_bar.get_title_widget()
        if isinstance(title_widget, Gtk.Box):
            # If we already have a box with title and subtitle
            pass
        else:
            # Create new title widget with subtitle
            title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            title_box.set_halign(Gtk.Align.CENTER)
            
            title_label = Gtk.Label(label=APPLICATION_TITLE)
            title_label.add_css_class("title")
            title_box.append(title_label)
            
            self.subtitle_label = Gtk.Label(label=f'{percent}% classified')
            self.subtitle_label.add_css_class("subtitle")
            title_box.append(self.subtitle_label)
            
            self.header_bar.set_title_widget(title_box)

        # Update existing subtitle
        if hasattr(self, 'subtitle_label'):
            self.subtitle_label.set_text(f'{percent}% classified')

    # Event handlers
    def _on_key_press_event(self, controller: Gtk.EventControllerKey, keyval: int, 
                           keycode: int, state: Gdk.ModifierType) -> bool:
        """Handle keyboard events."""
        return self.controller.handle_key_press(keyval, state)

    def _on_keep_clicked(self) -> None:
        """Handle keep button clicks."""
        self.controller.keep_current_image()

    def _on_discard_clicked(self) -> None:
        """Handle discard button clicks."""
        self.controller.discard_current_image()

    def _on_thumbnail_clicked(self, index: int) -> None:
        """Handle thumbnail clicks."""
        self.controller.navigate_to_image(index)

    def _on_scroll_navigation(self, next_image: bool) -> None:
        """Handle scroll navigation."""
        if next_image:
            self.controller.navigate_next()
        else:
            self.controller.navigate_previous()

    def _on_commit_clicked(self, button: Gtk.Button) -> None:
        """Handle commit button clicks."""
        self.commit_dialog.show_commit_confirmation()

    def _on_progress_updated(self, classified: int, total: int) -> None:
        """Handle progress updates."""
        self._update_progress_display()

    def _on_commit_complete(self) -> None:
        """Handle commit completion."""
        # Close the application
        self.get_application().quit()
