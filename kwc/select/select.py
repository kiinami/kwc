import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Gdk, GObject, Gio, Adw

from .utils import get_or_compute_hash, group_images_by_hash, get_all_images
from .widgets import LazyThumbnailButton, GroupThumbnailButton

import os
from pathlib import Path
import imagehash
from PIL import Image
from PIL import ExifTags

# Constants
THUMBNAIL_WIDTH = 160
THUMBNAIL_HEIGHT = 100
CROSSFADE_DURATION = 200  # milliseconds
SCROLL_ANIMATION_DURATION = 300  # milliseconds
SCROLL_ANIMATION_STEPS = 30
LAZY_LOAD_BUFFER = 200  # pixels

# Custom EXIF tag for hash (use UserComment if nothing else is available)
HASH_EXIF_TAG = None
for k, v in ExifTags.TAGS.items():
    if v == 'UserComment':
        HASH_EXIF_TAG = k
        break
HASH_EXIF_PREFIX = b'kwc_hash:'


# Load CSS for thumbnail coloring
def _load_css():
    """Load CSS styling for the application."""
    css_provider = Gtk.CssProvider()
    css_provider.load_from_path(str(Path(__file__).parent / "style.css"))
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(),
        css_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )

_load_css()


class ImageSelectorWindow(Adw.ApplicationWindow):
    """Main window for the image selector application (Adwaita style)."""

    def __init__(self, source_dir: Path, selected_dir: Path, discarded_dir: Path, hash_group_distance: int = 5, **kwargs):
        super().__init__(**kwargs, title='KWC Selector')
        self.set_focusable(True)
        self.connect('map', lambda *a: self.grab_focus())
        self.source_dir = source_dir
        self.selected_dir = selected_dir
        self.discarded_dir = discarded_dir
        self.hash_group_distance = hash_group_distance  # Configurable similarity threshold
        self.current_index = 0
        self.picture_path = None
        self.thumb_buttons = []
        self.undo_stack = []  # Stack to keep track of actions for undo

        # Use Adw.HeaderBar for a modern look
        self.header_bar = Adw.HeaderBar()
        self.header_bar.set_show_end_title_buttons(True)
        self.header_bar.set_show_start_title_buttons(True)
        self.header_bar.title = 'KWC Selector'
        self.header_bar.subtitle = '0% classified'

        # Undo button (Adwaita style)
        self.undo_button = Gtk.Button()
        icon = Gtk.Image.new_from_icon_name("edit-undo")
        self.undo_button.set_child(icon)
        self.undo_button.set_tooltip_text("Undo (Ctrl+Z)")
        self.undo_button.add_css_class("flat")
        self.undo_button.connect("clicked", lambda _: self.undo_last_action())
        self.header_bar.pack_start(self.undo_button)

        # Main content box: header bar + main content (use Adw.Bin for Adwaita)
        self._main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(self._main_vbox)
        self._main_vbox.append(self.header_bar)

        self._setup_ui()
        self._setup_images()
        self._setup_event_handlers()
        self.update_header_title()

    def update_header_title(self):
        """Update the header title and subtitle with classification progress."""
        total = len(self.all_images) if hasattr(self, 'all_images') else 0
        if total == 0:
            percent = 0
        else:
            classified = sum(1 for img in self.all_images if img.parent in (self.selected_dir, self.discarded_dir))
            percent = int(classified / total * 100)
        self.header_bar.title = 'KWC Selector'
        self.header_bar.subtitle = f'{percent}% classified'

    def _create_main_container(self):
        """Create and configure the main container box (Adwaita style)."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)
        box.add_css_class("boxed-list")
        return box

    def _create_image_stack(self):
        """Create the image stack for crossfade animations."""
        self.picture_stack = Gtk.Stack()
        self.picture_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.picture_stack.set_transition_duration(CROSSFADE_DURATION)

        self.picture_a = Gtk.Picture()
        self.picture_b = Gtk.Picture()
        self.picture_stack.add_child(self.picture_a)
        self.picture_stack.add_child(self.picture_b)
        self.current_picture = self.picture_a

    def _create_action_buttons(self):
        """Create the Keep/Discard action buttons (Adwaita style)."""
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        self.keep_button = Gtk.Button.new_with_label('Keep (q)')
        self.keep_button.add_css_class("suggested-action")
        self.keep_button.connect('clicked', lambda _: self.on_keep())
        keycont_keep = Gtk.EventControllerKey()
        keycont_keep.connect('key-pressed', self.on_key_press_event)
        self.keep_button.add_controller(keycont_keep)
        hbox.append(self.keep_button)

        self.discard_button = Gtk.Button.new_with_label('Discard (w)')
        self.discard_button.add_css_class("destructive-action")
        self.discard_button.connect('clicked', lambda _: self.on_discard())
        keycont_discard = Gtk.EventControllerKey()
        keycont_discard.connect('key-pressed', self.on_key_press_event)
        self.discard_button.add_controller(keycont_discard)
        hbox.append(self.discard_button)

        hbox.set_halign(Gtk.Align.CENTER)
        return hbox

    def _show_progress(self, fraction, eta=None):
        """Update and show the progress bar."""
        self.progressbar.set_fraction(fraction)
        percent = int(fraction * 100)
        if eta is not None:
            self.progressbar.set_text(f"{percent}%  (ETA: {eta:.1f}s)")
        else:
            self.progressbar.set_text(f"{percent}%")
        self.progressbar.show()
        while GObject.main_context_default().pending():
            GObject.main_context_default().iteration(False)

    def _hide_progress(self):
        """Hide the progress bar."""
        self.progressbar.hide()

    def _ensure_hashes_with_progress(self):
        """Compute image hashes with progress feedback."""
        import time
        total = len(self.all_images)
        start_time = time.time()
        for idx, img_path in enumerate(self.all_images):
            hashval = get_or_compute_hash(img_path)
            self.image_hashes[img_path] = hashval
            fraction = (idx + 1) / total if total else 1
            elapsed = time.time() - start_time
            eta = (elapsed / (idx + 1)) * (total - (idx + 1)) if idx > 0 else 0
            self._show_progress(fraction, eta)
        self._hide_progress()
        self.image_groups = group_images_by_hash(self.all_images, self.image_hashes, max_distance=self.hash_group_distance)
        self.populate_filmstrip()
        self.set_initial_selection()
        return False  # Stop idle_add loop

    def _create_filmstrip(self):
        """Create the filmstrip thumbnail viewer."""
        self.filmstrip_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.filmstrip_box.set_valign(Gtk.Align.CENTER)

        self.filmstrip_scroller = Gtk.ScrolledWindow()
        self.filmstrip_scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.filmstrip_scroller.set_child(self.filmstrip_box)
        self.filmstrip_scroller.set_min_content_height(100)

    def _setup_images(self):
        """Initialize images, compute hashes, and set initial selection."""
        self.all_images = get_all_images(self.source_dir, self.selected_dir, self.discarded_dir)
        self.image_hashes = {}
        # Show progress bar before hashing
        self.progressbar.set_fraction(0)
        self.progressbar.set_text("Hashing images...")
        self.progressbar.show()
        GObject.idle_add(self._ensure_hashes_with_progress)
        # The rest of setup will be called after hashing completes

    def _clear_filmstrip(self):
        """Remove all children from the filmstrip box."""
        child = self.filmstrip_box.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self.filmstrip_box.remove(child)
            child = next_child

    def _create_thumbnail_button(self, img, idx):
        """Create a single thumbnail button with appropriate styling."""
        button = LazyThumbnailButton(img, idx, self)
        button.connect('clicked', self.on_thumbnail_clicked, idx)

        # Apply initial styling based on image location
        if img.parent == self.selected_dir:
            button.set_css_classes(["thumb-selected"])
        elif img.parent == self.discarded_dir:
            button.set_css_classes(["thumb-discarded"])

        return button

    def _create_group_thumbnail_button(self, group, group_idx):
        """Create a thumbnail button for a group of images."""
        button = GroupThumbnailButton(group, group_idx, self)
        button.connect('clicked', self.on_group_thumbnail_clicked, group_idx)
        # Style if all images in group are selected/discarded
        if all(img.parent == self.selected_dir for img in group):
            button.set_css_classes(["thumb-selected"])
        elif all(img.parent == self.discarded_dir for img in group):
            button.set_css_classes(["thumb-discarded"])
        return button

    def populate_filmstrip(self):
        """Populate the filmstrip with group thumbnail buttons."""
        self._clear_filmstrip()
        self.thumb_buttons = []
        for group_idx, group in enumerate(self.image_groups):
            button = self._create_group_thumbnail_button(group, group_idx)
            self.filmstrip_box.append(button)
            self.thumb_buttons.append(button)
        GObject.idle_add(self.load_visible_thumbnails)
        self.update_header_title()

    def set_initial_selection(self):
        """Set the initial image selection, preferring images from source directory."""
        for i, img in enumerate(self.all_images):
            if img.parent == self.source_dir:
                self.current_index = i
                self.update_main_image(i)
                GObject.idle_add(self.center_filmstrip_on_selected, i, False)  # Jump instantly
                return

        # Fallback to first image if no source images found
        if self.all_images:
            self.current_index = 0
            self.update_main_image(0)
            GObject.idle_add(self.center_filmstrip_on_selected, 0, False)

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
            visible_width = hadj.get_page_size() or self.filmstrip_scroller.get_allocation().width or 1
            target_x = alloc.x + alloc.width // 2 - visible_width // 2
            target_x = max(0, min(target_x, hadj.get_upper() - visible_width))
            if animate:
                self._animate_scroll_to(hadj, target_x)
            else:
                hadj.set_value(target_x)

        return False

    def _animate_scroll_to(self, adjustment, target_value):
        """Animate smooth scrolling to a target position."""
        start_value = adjustment.get_value()
        diff = target_value - start_value

        if abs(diff) < 1:  # Already close enough
            adjustment.set_value(target_value)
            return

        step_time = SCROLL_ANIMATION_DURATION // SCROLL_ANIMATION_STEPS
        step_count = [0]  # Use list to make it mutable in closure

        def animate_step():
            step_count[0] += 1
            progress = step_count[0] / SCROLL_ANIMATION_STEPS

            # Easing function (ease-out cubic)
            eased_progress = 1 - (1 - progress) ** 3
            current_value = start_value + diff * eased_progress
            adjustment.set_value(current_value)

            if step_count[0] >= SCROLL_ANIMATION_STEPS:
                adjustment.set_value(target_value)
                GObject.idle_add(self.load_visible_thumbnails)
                return False  # Stop the timer
            return True  # Continue the timer

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
            if not button.is_loaded:
                alloc = button.get_allocation()
                button_start = alloc.x
                button_end = alloc.x + alloc.width

                # Check if button is within the loading area
                if button_end >= load_start and button_start <= load_end:
                    button.load_thumbnail()

        return False

    def on_thumbnail_clicked(self, button, idx):
        """Handle thumbnail button clicks."""
        self._navigate_to_image(idx)

    def on_group_thumbnail_clicked(self, button, group_idx):
        """Handle group thumbnail button clicks: select the first image in the group (robust to moves)."""
        group = self.image_groups[group_idx]
        # Try to find the first image in the group that is still in self.all_images (by name)
        idx = None
        for img in group:
            for i, aimg in enumerate(self.all_images):
                if aimg.name == img.name:
                    idx = i
                    break
            if idx is not None:
                break
        if idx is None:
            idx = 0  # fallback to first image
        self._navigate_to_image(idx)

    def _navigate_to_image(self, new_index):
        """Navigate to a specific image index."""
        if 0 <= new_index < len(self.all_images):
            self.current_index = new_index
            self.update_main_image(new_index)
            self.center_filmstrip_on_selected(new_index)
            return True
        return False

    def _move_image_to_directory(self, target_dir):
        """Move current image to target directory and update UI. Also record action for undo."""
        if self.picture_path.parent == target_dir:
            self.update_main_image(self.current_index)
            return
        dest = target_dir / self.picture_path.name
        # Record the action for undo (src, dest, index)
        self.undo_stack.append((self.picture_path, dest, self.current_index))
        os.rename(self.picture_path, dest)
        self.all_images[self.current_index] = dest
        self.thumb_buttons[self.current_index].update_image_path(dest)
        self._update_button_styles(self.current_index)
        self.update_main_image(self.current_index)
        GObject.idle_add(self.center_filmstrip_on_selected, self.current_index)
        self.update_header_title()

    def undo_last_action(self):
        """Undo the last image move action."""
        if not self.undo_stack:
            return
        src, dest, idx = self.undo_stack.pop()
        if dest.exists():
            os.rename(dest, src)
            self.all_images[idx] = src
            self.thumb_buttons[idx].update_image_path(src)
            self._update_button_styles(idx)
            self.update_main_image(idx)
            GObject.idle_add(self.center_filmstrip_on_selected, idx)
            self.update_header_title()

    def _update_button_styles(self, current_idx):
        """Update CSS classes for all thumbnail buttons."""
        for i, btn in enumerate(self.thumb_buttons):
            css_classes = []
            # Add base styling based on image location
            if self.all_images[i].parent == self.selected_dir:
                css_classes.append("thumb-selected")
            elif self.all_images[i].parent == self.discarded_dir:
                css_classes.append("thumb-discarded")
            # Add current selection styling
            if i == current_idx:
                css_classes.append("current-thumb")
            btn.set_css_classes(css_classes)

    def _update_action_button_styles(self, image_path):
        """Update CSS classes for Keep/Discard buttons."""
        if image_path.parent == self.selected_dir:
            self.keep_button.set_css_classes(["thumb-selected"])
            self.discard_button.set_css_classes([])
        elif image_path.parent == self.discarded_dir:
            self.keep_button.set_css_classes([])
            self.discard_button.set_css_classes(["thumb-discarded"])
        else:
            self.keep_button.set_css_classes([])
            self.discard_button.set_css_classes([])

    def on_key_press_event(self, controller, keyval, keycode, state, *args):
        """Handle keyboard input."""
        ctrl = state & Gdk.ModifierType.CONTROL_MASK
        if (keyval == Gdk.KEY_z or keycode == ord('z')) and ctrl:
            self.undo_last_action()
            return True
        if keyval == Gdk.KEY_Left:
            self._navigate_to_image(self.current_index - 1)
            return True
        elif keyval == Gdk.KEY_Right:
            self._navigate_to_image(self.current_index + 1)
            return True
        elif keycode == ord('q'):
            self.on_keep()
            return True
        elif keycode == ord('w'):
            self.on_discard()
            return True
        return False

    def update_main_image(self, idx):
        """Update the main image display and UI state."""
        image_path = self.all_images[idx]
        group_idx = None
        for i, group in enumerate(self.image_groups):
            if image_path in group:
                group_idx = i
                break
        if group_idx is not None:
            group = self.image_groups[group_idx]
        else:
            group = [image_path]
        # Remove any previous child from the main image area (GTK4 compatible)
        child = self._main_image_area.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._main_image_area.remove(child)
            child = next_child
        # Show grid if group has more than one image, else show single image
        if len(group) > 1:
            grid = Gtk.Grid()
            grid.set_row_spacing(12)
            grid.set_column_spacing(12)
            grid.set_hexpand(True)
            grid.set_vexpand(True)
            grid.set_halign(Gtk.Align.FILL)
            grid.set_valign(Gtk.Align.FILL)
            max_cols = 4
            for i, img_path in enumerate(group):
                pic = Gtk.Picture.new_for_file(Gio.File.new_for_path(str(img_path)))
                pic.set_size_request(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)
                pic.set_hexpand(True)
                pic.set_vexpand(True)
                pic.set_halign(Gtk.Align.FILL)
                pic.set_valign(Gtk.Align.FILL)
                grid.attach(pic, i % max_cols, i // max_cols, 1, 1)
            self._main_image_area.append(grid)
            self._current_group_grid = grid
        else:
            self.animate_image_transition(image_path)
            self.picture_stack.set_hexpand(True)
            self.picture_stack.set_vexpand(True)
            self.picture_stack.set_halign(Gtk.Align.FILL)
            self.picture_stack.set_valign(Gtk.Align.FILL)
            self._main_image_area.append(self.picture_stack)
            self._current_group_grid = None
        # Update all button styles
        self._update_button_styles(idx)
        self._update_action_button_styles(image_path)
        # Update current state
        self.current_index = idx
        self.picture_path = image_path

    def _find_next_unclassified_index(self, start_idx=None):
        """Find the next image not in selected or discarded directories."""
        if start_idx is None:
            start_idx = self.current_index
        n = len(self.all_images)
        for offset in range(1, n):
            idx = (start_idx + offset) % n
            parent = self.all_images[idx].parent
            if parent != self.selected_dir and parent != self.discarded_dir:
                return idx
        return None  # All images classified

    def on_keep(self):
        """Move current image to selected directory and skip to next unclassified image."""
        self._move_image_to_directory(self.selected_dir)
        next_idx = self._find_next_unclassified_index()
        if next_idx is not None:
            self.update_main_image(next_idx)
            GObject.idle_add(self.center_filmstrip_on_selected, next_idx)
        self.update_header_title()

    def on_discard(self):
        """Move current image to discarded directory and skip to next unclassified image."""
        self._move_image_to_directory(self.discarded_dir)
        next_idx = self._find_next_unclassified_index()
        if next_idx is not None:
            self.update_main_image(next_idx)
            GObject.idle_add(self.center_filmstrip_on_selected, next_idx)
        self.update_header_title()

    def on_filmstrip_scroll(self, controller, dx, dy):
        """Handle filmstrip scroll events to trigger lazy loading."""
        GObject.idle_add(self.load_visible_thumbnails)
        return False

    def on_scroll_value_changed(self, adjustment):
        """Handle scroll adjustment changes to trigger lazy loading."""
        GObject.idle_add(self.load_visible_thumbnails)

    def animate_image_transition(self, new_image_path):
        """Animate the transition between main images using crossfade effect."""
        # Use the non-visible picture for the new image
        next_picture = self.picture_b if self.current_picture == self.picture_a else self.picture_a
        self.current_picture = next_picture

        # Load new image into the hidden picture
        next_picture.set_filename(str(new_image_path))

        # Crossfade to the new picture
        self.picture_stack.set_visible_child(next_picture)

    def on_window_resize(self, *args):
        """Handle window resize events to update thumbnail visibility."""
        GObject.idle_add(self.load_visible_thumbnails)

    def on_scroller_focus_change(self, controller, *args):
        """Handle focus changes on the filmstrip scroller."""
        GObject.idle_add(self.load_visible_thumbnails)

    def delayed_initial_load(self):
        """Perform delayed initial loading of visible thumbnails."""
        GObject.idle_add(self.load_visible_thumbnails)
        return False  # Run once only

    def _setup_event_handlers(self):
        """Set up event handlers for the application."""
        # Add key event controller for the main window
        key_controller = Gtk.EventControllerKey()
        key_controller.connect('key-pressed', self.on_key_press_event)
        self.add_controller(key_controller)
        # Connect resize handler
        self.connect('notify::default-width', self.on_window_resize)
        self.connect('notify::default-height', self.on_window_resize)
        # Connect filmstrip scroll handlers
        scroll_controller = Gtk.EventControllerScroll()
        scroll_controller.set_flags(Gtk.EventControllerScrollFlags.BOTH_AXES)
        scroll_controller.connect('scroll', self.on_filmstrip_scroll)
        self.filmstrip_scroller.add_controller(scroll_controller)
        self.filmstrip_scroller.get_hadjustment().connect('value-changed', self.on_scroll_value_changed)

    def _setup_ui(self):
        """Initialize the main UI components."""
        main_box = self._create_main_container()
        self._main_vbox.append(main_box)

        # Create main image area container (fixed position, expands to fill)
        self._main_image_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._main_image_area.set_hexpand(True)
        self._main_image_area.set_vexpand(True)
        self._main_image_area.set_halign(Gtk.Align.FILL)
        self._main_image_area.set_valign(Gtk.Align.FILL)
        main_box.append(self._main_image_area)

        # Create image stack (for single image mode)
        self._create_image_stack()
        self.picture_stack.set_hexpand(True)
        self.picture_stack.set_vexpand(True)
        self.picture_stack.set_halign(Gtk.Align.FILL)
        self.picture_stack.set_valign(Gtk.Align.FILL)
        # Initially add the image stack to the main image area
        self._main_image_area.append(self.picture_stack)

        # Create progress bar (hidden by default)
        self.progressbar = Gtk.ProgressBar()
        self.progressbar.set_show_text(True)
        self.progressbar.set_hexpand(True)
        self.progressbar.set_vexpand(False)
        self.progressbar.set_margin_top(20)
        self.progressbar.set_margin_bottom(20)
        self.progressbar.set_margin_start(40)
        self.progressbar.set_margin_end(40)
        self.progressbar.set_valign(Gtk.Align.CENTER)
        self.progressbar.set_halign(Gtk.Align.FILL)
        self.progressbar.hide()
        main_box.append(self.progressbar)

        # Create action buttons
        button_box = self._create_action_buttons()
        main_box.append(button_box)

        # Create filmstrip (always at the bottom)
        self._create_filmstrip()
        main_box.append(self.filmstrip_scroller)

def select(source_dir: Path, selected_dir: Path, discarded_dir: Path, hash_group_distance: int = 5):
    """
    Main entry point for the image selector application.

    Args:
        source_dir: Directory containing source images
        selected_dir: Directory for selected/kept images
        discarded_dir: Directory for discarded images
        hash_group_distance: Perceptual hash distance threshold for grouping
    """
    # Ensure target directories exist
    selected_dir.mkdir(exist_ok=True)
    discarded_dir.mkdir(exist_ok=True)

    app = Adw.Application(application_id='com.kwc.Selector')
    def on_activate_with_distance(app, source_dir, selected_dir, discarded_dir, hash_group_distance):
        win = ImageSelectorWindow(source_dir, selected_dir, discarded_dir, hash_group_distance=hash_group_distance, application=app)
        win.present()
    app.connect('activate', on_activate_with_distance, source_dir, selected_dir, discarded_dir, hash_group_distance)
    app.run(None)
