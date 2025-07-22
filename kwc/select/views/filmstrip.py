"""
Filmstrip view component.

This module contains the filmstrip thumbnail navigation component.
"""

from pathlib import Path
from typing import List, Optional, Callable

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GObject

from ..widgets.lazy_thumbnail import LazyThumbnailButton
from ..utils.constants import SCROLL_ANIMATION_DURATION, SCROLL_ANIMATION_STEPS, LAZY_LOAD_BUFFER


class FilmstripView:
    """Filmstrip component for thumbnail navigation."""

    def __init__(self, on_thumbnail_clicked: Optional[Callable[[int], None]] = None,
                 on_scroll_navigation: Optional[Callable[[bool], None]] = None):
        """
        Initialize the filmstrip view.
        
        Args:
            on_thumbnail_clicked: Callback for thumbnail clicks
            on_scroll_navigation: Callback for scroll navigation (True=next, False=prev)
        """
        self._on_thumbnail_clicked = on_thumbnail_clicked
        self._on_scroll_navigation = on_scroll_navigation
        self._thumb_buttons: List[LazyThumbnailButton] = []
        
        self.widget = self._create_filmstrip()
        self._setup_event_handlers()

    def _create_filmstrip(self) -> Gtk.ScrolledWindow:
        """Create the filmstrip thumbnail viewer."""
        # Create the container for thumbnails
        self._filmstrip_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._filmstrip_box.set_valign(Gtk.Align.CENTER)

        # Create the scrolled window
        self._filmstrip_scroller = Gtk.ScrolledWindow()
        self._filmstrip_scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self._filmstrip_scroller.add_css_class("filmstrip-scroller")
        self._filmstrip_scroller.set_child(self._filmstrip_box)
        self._filmstrip_scroller.set_min_content_height(100)

        return self._filmstrip_scroller

    def _clear_filmstrip(self) -> None:
        """Remove all children from the filmstrip box."""
        child = self._filmstrip_box.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._filmstrip_box.remove(child)
            child = next_child

    def _create_thumbnail_button(self, img: Path, idx: int) -> LazyThumbnailButton:
        """Create a single thumbnail button with appropriate styling."""
        button = LazyThumbnailButton(
            img, idx, 
            on_clicked=self._on_thumbnail_clicked if self._on_thumbnail_clicked else None
        )
        return button

    def populate_filmstrip(self, all_images: List[Path], selected_dir: Path, discarded_dir: Path) -> None:
        """
        Populate the filmstrip with thumbnail buttons.
        
        Args:
            all_images: List of all image paths
            selected_dir: Directory containing selected images
            discarded_dir: Directory containing discarded images
        """
        self._clear_filmstrip()
        self._thumb_buttons = []
        
        for idx, img in enumerate(all_images):
            button = self._create_thumbnail_button(img, idx)
            
            # Apply initial styling based on image location
            if img.parent == selected_dir:
                button.add_css_class("thumb-selected")
            elif img.parent == discarded_dir:
                button.add_css_class("thumb-discarded")
                
            self._filmstrip_box.append(button)
            self._thumb_buttons.append(button)
        
        # Load visible thumbnails after a brief delay
        GObject.idle_add(self.load_visible_thumbnails)

    def center_filmstrip_on_selected(self, idx: int) -> None:
        """
        Center the filmstrip view on the selected thumbnail.
        
        Args:
            idx: Index of the thumbnail to center on
        """
        if not (0 <= idx < len(self._thumb_buttons)):
            return
            
        button = self._thumb_buttons[idx]
        
        # Ensure the selected thumbnail is loaded
        if not button.is_loaded:
            button.load_thumbnail()
            
        alloc = button.get_allocation()
        hadj = self._filmstrip_scroller.get_hadjustment()
        
        if hadj:
            target = alloc.x + alloc.width / 2 - hadj.get_page_size() / 2
            self._animate_scroll_to(hadj, target)

    def _animate_scroll_to(self, adjustment: Gtk.Adjustment, target_value: float) -> None:
        """Animate smooth scrolling to a target position."""
        start_value = adjustment.get_value()
        diff = target_value - start_value
        
        if abs(diff) < 1:
            adjustment.set_value(target_value)
            return
            
        step_time = SCROLL_ANIMATION_DURATION // SCROLL_ANIMATION_STEPS
        step_count = [0]  # Use list to make it mutable in closure
        
        def animate_step():
            frac = min(1, step_count[0] / SCROLL_ANIMATION_STEPS)
            value = start_value + diff * frac
            adjustment.set_value(value)
            step_count[0] += 1
            if frac < 1:
                GObject.timeout_add(step_time, animate_step)
                
        GObject.timeout_add(step_time, animate_step)

    def load_visible_thumbnails(self) -> bool:
        """Load thumbnails that are currently visible or near-visible in the filmstrip."""
        hadj = self._filmstrip_scroller.get_hadjustment()
        if not hadj:
            return False
            
        visible_start = hadj.get_value()
        visible_width = hadj.get_page_size()
        visible_end = visible_start + visible_width
        
        # Add buffer to load thumbnails slightly outside the visible area
        load_start = visible_start - LAZY_LOAD_BUFFER
        load_end = visible_end + LAZY_LOAD_BUFFER
        
        for button in self._thumb_buttons:
            alloc = button.get_allocation()
            if alloc.x + alloc.width > load_start and alloc.x < load_end:
                button.load_thumbnail()
                
        return False

    def update_button_styles(self, current_idx: int, selected_dir: Path, 
                           discarded_dir: Path, all_images: List[Path]) -> None:
        """
        Update thumbnail button styles based on current selection and image locations.
        
        Args:
            current_idx: Index of currently selected image
            selected_dir: Directory containing selected images
            discarded_dir: Directory containing discarded images
            all_images: List of all image paths
        """
        for idx, button in enumerate(self._thumb_buttons):
            # Remove old classes
            button.remove_css_class("current-thumb")
            button.remove_css_class("thumb-selected")
            button.remove_css_class("thumb-discarded")
            
            # Add current thumb styling
            if idx == current_idx:
                button.add_css_class("current-thumb")
            
            # Add location-based styling
            if idx < len(all_images):
                img = all_images[idx]
                if img.parent == selected_dir:
                    button.add_css_class("thumb-selected")
                elif img.parent == discarded_dir:
                    button.add_css_class("thumb-discarded")

    def _on_filmstrip_scroll(self, controller: Gtk.EventControllerScroll, dx: float, dy: float) -> bool:
        """Handle scroll events for navigation."""
        if self._on_scroll_navigation:
            if dy < 0:
                self._on_scroll_navigation(False)  # Previous
            elif dy > 0:
                self._on_scroll_navigation(True)   # Next
        return True

    def _on_scroll_value_changed(self, adjustment: Gtk.Adjustment) -> None:
        """Handle scroll value changes for lazy loading."""
        GObject.idle_add(self.load_visible_thumbnails)

    def _setup_event_handlers(self) -> None:
        """Set up event handlers for the filmstrip."""
        # These will be connected after the widget is fully initialized
        pass

    def connect_events(self) -> None:
        """Connect events after widgets are created and added to layout."""
        # Scroll controller for navigation
        scroll_controller = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll_controller.connect('scroll', self._on_filmstrip_scroll)
        self._filmstrip_scroller.add_controller(scroll_controller)
        
        # Adjustment change handler for lazy loading
        hadj = self._filmstrip_scroller.get_hadjustment()
        hadj.connect('value-changed', self._on_scroll_value_changed)
        
        # Focus controller for lazy loading
        focus_controller = Gtk.EventControllerFocus()
        focus_controller.connect('enter', lambda *args: GObject.idle_add(self.load_visible_thumbnails))
        self._filmstrip_scroller.add_controller(focus_controller)
