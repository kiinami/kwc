# Standard library imports
from pathlib import Path
from typing import List, Optional

# Third-party imports
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GObject

# Local imports
from .widgets import LazyThumbnailButton
from .constants import SCROLL_ANIMATION_DURATION, SCROLL_ANIMATION_STEPS, LAZY_LOAD_BUFFER


class Filmstrip:
    """Filmstrip component for thumbnail navigation."""

    def __init__(self, parent_window):
        self.parent_window = parent_window
        self.thumb_buttons: List[LazyThumbnailButton] = []
        self.filmstrip_box = None
        self.filmstrip_scroller = None
        self._create_filmstrip()
        self._setup_event_handlers()

    def _create_filmstrip(self):
        """Create the filmstrip thumbnail viewer."""
        self.filmstrip_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.filmstrip_box.set_valign(Gtk.Align.CENTER)

        self.filmstrip_scroller = Gtk.ScrolledWindow()
        self.filmstrip_scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.filmstrip_scroller.add_css_class("filmstrip-scroller")
        self.filmstrip_scroller.set_child(self.filmstrip_box)
        self.filmstrip_scroller.set_min_content_height(100)

    def _clear_filmstrip(self):
        """Remove all children from the filmstrip box."""
        child = self.filmstrip_box.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self.filmstrip_box.remove(child)
            child = next_child

    def _create_thumbnail_button(self, img, idx):
        """Create a single thumbnail button with appropriate styling."""
        button = LazyThumbnailButton(img, idx, self.parent_window)
        button.connect('clicked', self.on_thumbnail_clicked, idx)
        # Apply initial styling based on image location
        if img.parent == self.parent_window.selected_dir:
            button.add_css_class("thumb-selected")
        elif img.parent == self.parent_window.discarded_dir:
            button.add_css_class("thumb-discarded")
        return button

    def populate_filmstrip(self, all_images: List[Path]):
        """Populate the filmstrip with thumbnail buttons."""
        self._clear_filmstrip()
        self.thumb_buttons = []
        for idx, img in enumerate(all_images):
            button = self._create_thumbnail_button(img, idx)
            self.filmstrip_box.append(button)
            self.thumb_buttons.append(button)
        GObject.idle_add(self.load_visible_thumbnails)
        self.parent_window.update_header_title()

    def center_filmstrip_on_selected(self, idx, animate=True):
        """Center the filmstrip view on the selected thumbnail, optionally with animation."""
        if not (0 <= idx < len(self.thumb_buttons)):
            return False
        button = self.thumb_buttons[idx]
        # Ensure the selected thumbnail is loaded
        if not button.is_loaded:
            button.load_thumbnail()
        alloc = button.get_allocation()
        hadj = self.filmstrip_scroller.get_hadjustment()
        if hadj:
            target = alloc.x + alloc.width / 2 - hadj.get_page_size() / 2
            self._animate_scroll_to(hadj, target)
        return False

    def _animate_scroll_to(self, adjustment, target_value):
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

    def load_visible_thumbnails(self):
        """Load thumbnails that are currently visible or near-visible in the filmstrip."""
        hadj = self.filmstrip_scroller.get_hadjustment()
        if not hadj:
            return False
        visible_start = hadj.get_value()
        visible_width = hadj.get_page_size()
        visible_end = visible_start + visible_width
        # Add buffer to load thumbnails slightly outside the visible area
        load_start = visible_start - LAZY_LOAD_BUFFER
        load_end = visible_end + LAZY_LOAD_BUFFER
        for button in self.thumb_buttons:
            alloc = button.get_allocation()
            if alloc.x + alloc.width > load_start and alloc.x < load_end:
                button.load_thumbnail()
        return False

    def update_button_styles(self, current_idx, selected_dir: Path, discarded_dir: Path, all_images: List[Path]):
        """Update thumbnail button styles based on current selection and image locations."""
        for idx, button in enumerate(self.thumb_buttons):
            button.remove_css_class("current-thumb")
            if idx == current_idx:
                button.add_css_class("current-thumb")
            # Update selected/discarded styles
            button.remove_css_class("thumb-selected")
            button.remove_css_class("thumb-discarded")
            img = all_images[idx]
            if img.parent == selected_dir:
                button.add_css_class("thumb-selected")
            elif img.parent == discarded_dir:
                button.add_css_class("thumb-discarded")

    def on_thumbnail_clicked(self, button, idx):
        """Handle thumbnail button clicks."""
        self.parent_window._navigate_to_image(idx)

    def on_filmstrip_scroll(self, controller, dx, dy):
        """Handle scroll events for navigation."""
        if dy < 0:
            self.parent_window._navigate_to_image(max(0, self.parent_window.current_index - 1))
        elif dy > 0:
            self.parent_window._navigate_to_image(min(len(self.parent_window.all_images) - 1, self.parent_window.current_index + 1))
        return True

    def on_scroll_value_changed(self, adjustment):
        """Handle scroll value changes for lazy loading."""
        GObject.idle_add(self.load_visible_thumbnails)

    def on_window_resize(self, widget, param):
        """Handle window resize for lazy loading."""
        GObject.idle_add(self.load_visible_thumbnails)

    def on_scroller_focus_change(self, controller, *args):
        """Handle focus changes for lazy loading."""
        GObject.idle_add(self.load_visible_thumbnails)

    def _setup_event_handlers(self):
        """Connect scroll and resize events."""
        # These will be connected after the widget is created
        pass

    def connect_events(self):
        """Connect events after widgets are created and added to layout."""
        scroll_controller = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll_controller.connect('scroll', self.on_filmstrip_scroll)
        self.filmstrip_scroller.add_controller(scroll_controller)
        
        hadj = self.filmstrip_scroller.get_hadjustment()
        hadj.connect('value-changed', self.on_scroll_value_changed)
        
        focus_controller = Gtk.EventControllerFocus()
        focus_controller.connect('enter', self.on_scroller_focus_change)
        self.filmstrip_scroller.add_controller(focus_controller)
