"""
Main application class for KWC Selector.

This module contains the main application class that manages the overall
application lifecycle and window creation.
"""

from pathlib import Path
from typing import Optional

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw

from .views.main_window import MainWindow
from .utils.constants import APPLICATION_ID


class SelectorApplication(Adw.Application):
    """Main application class for the KWC Selector."""

    def __init__(self, source_dir: Path, selected_dir: Path, discarded_dir: Path):
        """
        Initialize the application.
        
        Args:
            source_dir: Directory containing source images
            selected_dir: Directory for selected/kept images  
            discarded_dir: Directory for discarded images
        """
        super().__init__(application_id=APPLICATION_ID)
        
        # Ensure target directories exist
        selected_dir.mkdir(exist_ok=True)
        discarded_dir.mkdir(exist_ok=True)
        
        self.source_dir = source_dir
        self.selected_dir = selected_dir
        self.discarded_dir = discarded_dir
        self.main_window: Optional[MainWindow] = None
        
        self.connect('activate', self._on_activate)

    def _on_activate(self, app: Adw.Application) -> None:
        """Handle application activation by creating the main window."""
        if not self.main_window:
            self.main_window = MainWindow(
                application=app,
                source_dir=self.source_dir,
                selected_dir=self.selected_dir,
                discarded_dir=self.discarded_dir
            )
        
        self.main_window.present()

    def run_app(self) -> int:
        """Run the application and return exit code."""
        return self.run(None)
