"""
Main entry point for the KWC Selector application.

This module provides the main entry function for the image selection interface.
"""

from pathlib import Path

from .application import SelectorApplication


def select(source_dir: Path, selected_dir: Path, discarded_dir: Path) -> int:
    """
    Main entry point for the image selector application.

    Args:
        source_dir: Directory containing source images
        selected_dir: Directory for selected/kept images
        discarded_dir: Directory for discarded images
        
    Returns:
        Application exit code
    """
    app = SelectorApplication(source_dir, selected_dir, discarded_dir)
    return app.run_app()
