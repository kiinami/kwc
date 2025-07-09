import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GObject, Gio

import os
from pathlib import Path

# Constants
THUMBNAIL_WIDTH = 160
THUMBNAIL_HEIGHT = 100
CROSSFADE_DURATION = 200  # milliseconds
SCROLL_ANIMATION_DURATION = 300  # milliseconds
SCROLL_ANIMATION_STEPS = 30
LAZY_LOAD_BUFFER = 200  # pixels
INITIAL_LOAD_DELAY = 100  # milliseconds


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


class LazyThumbnailButton(Gtk.Button):
    """A button that lazy-loads thumbnail images for performance."""

    def __init__(self, image_path, index, parent_window):
        super().__init__()
        self.image_path = image_path
        self.index = index
        self.parent_window = parent_window
        self.is_loaded = False
        self.picture = None

        self._create_placeholder()
        self.set_size_request(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)

    def _create_placeholder(self):
        """Create a placeholder widget while the thumbnail loads."""
        placeholder = Gtk.Box()
        placeholder.set_size_request(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)
        placeholder.add_css_class("thumbnail-placeholder")
        self.set_child(placeholder)

    def load_thumbnail(self):
        """Load the actual thumbnail image."""
        if not self.is_loaded:
            file = Gio.File.new_for_path(str(self.image_path))
            self.picture = Gtk.Picture.new_for_file(file)
            self.picture.set_size_request(THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)
            self.set_child(self.picture)
            self.is_loaded = True

    def update_image_path(self, new_path):
        """Update the image path and reload if necessary."""
        self.image_path = new_path
        if self.is_loaded:
            self.is_loaded = False
            self.load_thumbnail()


class ImageSelectorWindow(Gtk.ApplicationWindow):
    """Main window for the image selector application."""

    def __init__(self, source_dir: Path, selected_dir: Path, discarded_dir: Path, **kwargs):
        super().__init__(**kwargs, title='KWC Selector')
        self.source_dir = source_dir
        self.selected_dir = selected_dir
        self.discarded_dir = discarded_dir
        self.current_index = 0
        self.picture_path = None
        self.thumb_buttons = []
        self.undo_stack = []  # Stack to keep track of actions for undo

        # Create a modern GTK4 header bar with a dynamic, bold title and subtitle
        self.header_bar = Gtk.HeaderBar()
        self.title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.title_box.set_valign(Gtk.Align.CENTER)
        self.title_label = Gtk.Label()
        self.title_label.set_markup('<b>KWC Selector</b>')
        self.subtitle_label = Gtk.Label()
        self.subtitle_label.set_margin_top(2)
        self.subtitle_label.set_margin_bottom(2)
        self.subtitle_label.set_css_classes(["dim-label"])  # Optionally style subtitle
        self.title_box.append(self.title_label)
        self.title_box.append(self.subtitle_label)
        self.header_bar.set_title_widget(self.title_box)
        self.header_bar.set_show_title_buttons(True)

        # Add Undo button to the left side of the header bar
        self.undo_button = Gtk.Button()
        icon = Gtk.Image.new_from_icon_name("edit-undo")
        self.undo_button.set_child(icon)
        self.undo_button.set_tooltip_text("Undo (Ctrl+Z)")
        self.undo_button.connect("clicked", lambda _: self.undo_last_action())
        self.header_bar.pack_start(self.undo_button)

        self.set_titlebar(self.header_bar)

        self._setup_ui()
        self._setup_images()
        self._setup_event_handlers()
        self.update_header_title()

    def update_header_title(self):
        total = len(self.all_images) if hasattr(self, 'all_images') else 0
        if total == 0:
            percent = 0
        else:
            classified = sum(1 for img in self.all_images if img.parent in (self.selected_dir, self.discarded_dir))
            percent = int(classified / total * 100)
        self.title_label.set_markup('<b>KWC Selector</b>')
        self.subtitle_label.set_text(f'{percent}% classified')

    def _setup_ui(self):
        """Initialize the main UI components."""
        main_box = self._create_main_container()
        self.set_child(main_box)

        # Create main image display
        self._create_image_stack()
        main_box.append(self.picture_stack)

        # Create action buttons
        button_box = self._create_action_buttons()
        main_box.append(button_box)

        # Create filmstrip
        self._create_filmstrip()
        main_box.append(self.filmstrip_scroller)

    def _create_main_container(self):
        """Create and configure the main container box."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)
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
        """Create the Keep/Discard action buttons."""
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self.keep_button = Gtk.Button.new_with_label('Keep (q)')
        self.keep_button.connect('clicked', lambda _: self.on_keep())
        hbox.append(self.keep_button)

        self.discard_button = Gtk.Button.new_with_label('Discard (w)')
        self.discard_button.connect('clicked', lambda _: self.on_discard())
        hbox.append(self.discard_button)

        hbox.set_halign(Gtk.Align.CENTER)
        return hbox

    def _create_filmstrip(self):
        """Create the filmstrip thumbnail viewer."""
        self.filmstrip_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.filmstrip_box.set_valign(Gtk.Align.CENTER)

        self.filmstrip_scroller = Gtk.ScrolledWindow()
        self.filmstrip_scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.filmstrip_scroller.set_child(self.filmstrip_box)
        self.filmstrip_scroller.set_min_content_height(100)

    def _setup_images(self):
        """Initialize images and set initial selection."""
        self.all_images = self.get_all_images()
        self.populate_filmstrip()
        self.set_initial_selection()

    def _setup_event_handlers(self):
        """Setup all event handlers and controllers."""
        # Keyboard events
        keycont = Gtk.EventControllerKey()
        keycont.connect('key-pressed', self.on_key_press_event)
        self.add_controller(keycont)

        # Scroll events for lazy loading
        self.filmstrip_scroller.connect('scroll-child', self.on_filmstrip_scroll)
        hadj = self.filmstrip_scroller.get_hadjustment()
        if hadj:
            hadj.connect('value-changed', self.on_scroll_value_changed)

        # Window resize events
        self.connect('notify::default-width', self.on_window_resize)
        self.connect('notify::default-height', self.on_window_resize)

        # Focus events for filmstrip
        size_controller = Gtk.EventControllerFocus()
        size_controller.connect('enter', self.on_scroller_focus_change)
        size_controller.connect('leave', self.on_scroller_focus_change)
        self.filmstrip_scroller.add_controller(size_controller)

        # Delayed initial load
        GObject.timeout_add(INITIAL_LOAD_DELAY, self.delayed_initial_load)

    def get_all_images(self):
        """Collect and sort all images from all directories."""
        images = list(self.source_dir.glob('*.jpg'))
        images += list(self.selected_dir.glob('*.jpg'))
        images += list(self.discarded_dir.glob('*.jpg'))
        images = sorted(images, key=lambda x: int(x.stem.split('_')[-1]))
        return images

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

    def populate_filmstrip(self):
        """Populate the filmstrip with thumbnail buttons."""
        self._clear_filmstrip()

        self.thumb_buttons = []
        for idx, img in enumerate(self.all_images):
            button = self._create_thumbnail_button(img, idx)
            self.filmstrip_box.append(button)
            self.thumb_buttons.append(button)

        # Load thumbnails that are initially visible
        GObject.idle_add(self.load_visible_thumbnails)
        self.update_header_title()

    def set_initial_selection(self):
        """Set the initial image selection, preferring images from source directory."""
        for i, img in enumerate(self.all_images):
            if img.parent == self.source_dir:
                self.current_index = i
                self.update_main_image(i)
                GObject.idle_add(self.center_filmstrip_on_selected, i)
                return

        # Fallback to first image if no source images found
        if self.all_images:
            self.current_index = 0
            self.update_main_image(0)
            GObject.idle_add(self.center_filmstrip_on_selected, 0)

    def center_filmstrip_on_selected(self, idx):
        """Center the filmstrip view on the selected thumbnail with smooth animation."""
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
            self._animate_scroll_to(hadj, target_x)

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
            # Already in target directory, just update UI
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

    def on_key_press_event(self, keyval, keycode, state, *args):
        """Handle keyboard input."""
        ctrl = state & Gdk.ModifierType.CONTROL_MASK
        if (keyval == Gdk.KEY_z or keycode == ord('z')) and ctrl:
            self.undo_last_action()
            return True
        if keyval == Gdk.KEY_Left:
            return self._navigate_to_image(self.current_index - 1)
        elif keyval == Gdk.KEY_Right:
            return self._navigate_to_image(self.current_index + 1)
        elif keycode == ord('q'):
            self.on_keep()
            return True
        elif keycode == ord('w'):
            self.on_discard()
            return True
        return False

    def update_main_image(self, idx):
        """Update the main image display and UI state."""
        path = self.all_images[idx]

        # Animate the main image transition
        self.animate_image_transition(path)

        # Update all button styles
        self._update_button_styles(idx)
        self._update_action_button_styles(path)

        # Update current state
        self.current_index = idx
        self.picture_path = path

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

    def on_filmstrip_scroll(self, *args):
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


def on_activate(app, source_dir: Path, selected_dir: Path, discarded_dir: Path):
    """Create and present the main window when the application activates."""
    win = ImageSelectorWindow(source_dir, selected_dir, discarded_dir, application=app)
    win.present()


def select(source_dir: Path, selected_dir: Path, discarded_dir: Path):
    """
    Main entry point for the image selector application.

    Args:
        source_dir: Directory containing source images
        selected_dir: Directory for selected/kept images
        discarded_dir: Directory for discarded images
    """
    # Ensure target directories exist
    selected_dir.mkdir(exist_ok=True)
    discarded_dir.mkdir(exist_ok=True)

    app = Gtk.Application(application_id='com.kwc.Selector')
    app.connect('activate', on_activate, source_dir, selected_dir, discarded_dir)
    app.run(None)
