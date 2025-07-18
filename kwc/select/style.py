# style.py -- CSS loading for the KWC Selector app
from pathlib import Path
from gi.repository import Gtk, Gdk

def load_css():
    """Load CSS styling for the application."""
    css_provider = Gtk.CssProvider()
    css_provider.load_from_path(str(Path(__file__).parent / "style.css"))
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(),
        css_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
