"""
CSS styling utilities for KWC Selector.

This module handles loading and managing CSS styles for the application.
"""

from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk


def load_application_css() -> None:
    """Load CSS styling for the application."""
    css_path = Path(__file__).parent.parent / "resources" / "style.css"
    
    if not css_path.exists():
        print(f"Warning: CSS file not found at {css_path}")
        return
    
    try:
        css_provider = Gtk.CssProvider()
        css_provider.load_from_path(str(css_path))
        
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
    except Exception as e:
        print(f"Error loading CSS: {e}")
