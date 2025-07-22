# Standard library imports
from pathlib import Path

# Third-party imports
import gi
# Specify required versions before importing Gtk and Adw
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Gdk, GObject, Gio, Adw

# Local imports
from .widgets import LazyThumbnailButton
from .constants import CROSSFADE_DURATION, SCROLL_ANIMATION_DURATION, SCROLL_ANIMATION_STEPS, LAZY_LOAD_BUFFER
from .style import load_css
from .actionbar import ActionBar
from .filmstrip import Filmstrip
from .dialogs import CommitDialog

# CSS loading
load_css()


def get_all_images(source_dir: Path, selected_dir: Path, discarded_dir: Path) -> list[Path]:
    """Get all .jpg images from the three directories, sorted by numeric suffix."""
    images = sorted(list(source_dir.glob('*.jpg')) + list(selected_dir.glob('*.jpg')) + list(discarded_dir.glob('*.jpg')), key=lambda x: int(x.stem.split('_')[-1]))
    return images


class ImageSelectorWindow(Adw.ApplicationWindow):
    """Main window for the image selector application (Adwaita style)."""

    def __init__(self, source_dir: Path, selected_dir: Path, discarded_dir: Path, **kwargs):
        super().__init__(**kwargs, title='KWC Selector')
        # State variables
        self.source_dir: Path = source_dir
        self.selected_dir: Path = selected_dir
        self.discarded_dir: Path = discarded_dir
        self.current_index: int = 0  # Index of the currently displayed image
        self.picture_path: Path | None = None  # Path of the current image
        self.undo_stack: list = []  # Stack of (src, dest, index) for undo

        # Initialize components
        self.action_bar = ActionBar(self)
        self.filmstrip = Filmstrip(self)
        self.commit_dialog = CommitDialog(self)

        self._init_header_bar()
        self._setup_images()
        self._init_main_layout()
        self.update_header_title()

    def _init_header_bar(self):
        """Create and configure the Adw.HeaderBar."""
        self.header_bar = Adw.HeaderBar()
        self.header_bar.set_show_end_title_buttons(True)
        self.header_bar.set_show_start_title_buttons(True)
        self.header_bar.title = 'KWC Selector'
        self.header_bar.subtitle = '0% classified'

        # Add Commit button (text-only)
        self.commit_button = Gtk.Button.new_with_label("Commit")
        self.commit_button.set_can_focus(True)
        self.commit_button.set_sensitive(True)  # Always enabled
        self.commit_button.connect("clicked", self.on_commit_clicked)
        self.header_bar.pack_start(self.commit_button)

        self.undo_button = Gtk.Button()
        icon = Gtk.Image.new_from_icon_name("edit-undo")
        self.undo_button.set_child(icon)
        self.undo_button.set_tooltip_text("Undo (Ctrl+Z)")
        self.undo_button.add_css_class("flat")
        self.undo_button.connect("clicked", lambda _: self.undo_last_action())
        self.header_bar.pack_start(self.undo_button)

    def _init_main_layout(self):
        """Create the main vertical layout and add the header bar."""
        self._main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(self._main_vbox)
        self._main_vbox.append(self.header_bar)
        # Main image area
        self._create_image_stack()
        self.picture_stack.set_vexpand(True)
        self._main_vbox.append(self.picture_stack)

        # Action buttons (Keep/Discard)
        self._main_vbox.append(self.action_bar.widget)

        # Filmstrip
        self._main_vbox.append(self.filmstrip.filmstrip_scroller)
        self._setup_event_handlers()
        # Now that filmstrip UI exists, populate it
        self.filmstrip.populate_filmstrip(self.all_images)
        self.set_initial_selection()

    def update_header_title(self) -> None:
        """Update the header title and subtitle with classification progress."""
        total = len(self.all_images) if hasattr(self, 'all_images') else 0
        if total == 0:
            percent = 0
        else:
            classified = sum(1 for img in self.all_images if img.parent in [self.selected_dir, self.discarded_dir])
            percent = int((classified / total) * 100)
        self.header_bar.title = 'KWC Selector'
        self.header_bar.subtitle = f'{percent}% classified'

    def _create_image_stack(self) -> None:
        """Create the image stack for crossfade animations."""
        self.picture_stack = Gtk.Stack()
        self.picture_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.picture_stack.set_transition_duration(CROSSFADE_DURATION)
        self.picture_a = Gtk.Picture()
        self.picture_b = Gtk.Picture()
        # Ensure pictures and stack do not expand horizontally
        self.picture_stack.set_hexpand(False)
        self.picture_stack.set_halign(Gtk.Align.CENTER)
        self.picture_stack.set_valign(Gtk.Align.CENTER)
        self.picture_a.set_hexpand(False)
        self.picture_a.set_halign(Gtk.Align.CENTER)
        self.picture_b.set_hexpand(False)
        self.picture_b.set_halign(Gtk.Align.CENTER)
        self.picture_stack.add_child(self.picture_a)
        self.picture_stack.add_child(self.picture_b)
        self.current_picture = self.picture_a
        # Add vertical margins for separation from header and filmstrip
        self.picture_stack.set_margin_top(16)
        self.picture_stack.set_margin_bottom(16)
        self.picture_stack.add_css_class("main-image-stack")





    def _setup_images(self):
        """Set up image list and start hash computation with progress."""
        self.all_images = get_all_images(self.source_dir, self.selected_dir, self.discarded_dir)







    def set_initial_selection(self):
        """Set the initial image selection, preferring images from source directory."""
        for i, img in enumerate(self.all_images):
            if img.parent == self.source_dir:
                self._navigate_to_image(i)
                return
        # Fallback to first image if no source images found
        if self.all_images:
            self._navigate_to_image(0)









    def _navigate_to_image(self, new_index: int):
        """Navigate to a specific image index."""
        if not self.all_images:
            return False
        if 0 <= new_index < len(self.all_images):
            self.current_index = new_index
            self.picture_path = self.all_images[new_index]
            try:
                self.update_main_image(new_index)
            except Exception as e:
                print(f"Error updating main image: {e}")
            self.filmstrip.update_button_styles(new_index, self.selected_dir, self.discarded_dir, self.all_images)
            self.action_bar.update_button_states(self.picture_path, self.selected_dir, self.discarded_dir)
            self.filmstrip.center_filmstrip_on_selected(new_index)
        return False

    def _move_image_to_directory(self, target_dir: Path):
        """Move current image to target directory and update UI. Also record action for undo."""
        if self.picture_path is None or self.picture_path.parent == target_dir:
            return
        dest = target_dir / self.picture_path.name
        try:
            self.undo_stack.append((self.picture_path, dest, self.current_index))
            self.picture_path.rename(dest)
            self.all_images[self.current_index] = dest
            self.picture_path = dest
            self.filmstrip.update_button_styles(self.current_index, self.selected_dir, self.discarded_dir, self.all_images)
            self.action_bar.update_button_states(self.picture_path, self.selected_dir, self.discarded_dir)
            self.update_header_title()
        except Exception as e:
            print(f"Error moving {self.picture_path} to {dest}: {e}")

    def undo_last_action(self):
        """Undo the last image move action."""
        if not self.undo_stack:
            return
        src, dest, idx = self.undo_stack.pop()
        try:
            if dest.exists():
                dest.rename(src)
                self.all_images[idx] = src
                self.picture_path = src
                self.filmstrip.update_button_styles(idx, self.selected_dir, self.discarded_dir, self.all_images)
                self.action_bar.update_button_states(src, self.selected_dir, self.discarded_dir)
                self.update_header_title()
        except Exception as e:
            print(f"Error undoing move from {dest} to {src}: {e}")

    



    def on_key_press_event(self, controller, keyval, keycode, state, *args):
        # Handle key events for navigation and actions
        if keyval == Gdk.KEY_q:
            self.action_bar.on_keep()
            return True
        elif keyval == Gdk.KEY_w:
            self.action_bar.on_discard()
            return True
        elif keyval == Gdk.KEY_z and (state & Gdk.ModifierType.CONTROL_MASK):
            self.undo_last_action()
            return True
        elif keyval == Gdk.KEY_Left:
            self._navigate_to_image(max(0, self.current_index - 1))
            return True
        elif keyval == Gdk.KEY_Right:
            self._navigate_to_image(min(len(self.all_images) - 1, self.current_index + 1))
            return True
        return False

    def update_main_image(self, idx):
        # Update the main image display
        img_path = self.all_images[idx]
        file = Gio.File.new_for_path(str(img_path))
        if self.current_picture == self.picture_a:
            self.picture_b.set_file(file)
            self.picture_stack.set_visible_child(self.picture_b)
            self.current_picture = self.picture_b
        else:
            self.picture_a.set_file(file)
            self.picture_stack.set_visible_child(self.picture_a)
            self.current_picture = self.picture_a

    def _find_next_unclassified_index(self, start_idx=None):
        # Find the next image in source_dir
        if start_idx is None:
            start_idx = self.current_index + 1
        for i in range(start_idx, len(self.all_images)):
            if self.all_images[i].parent == self.source_dir:
                return i
        return None

    def _setup_event_handlers(self):
        """Connect scroll and resize events."""
        self.filmstrip.connect_events()
        # Connect window resize events to filmstrip
        self._main_vbox.connect('notify::allocation', self.filmstrip.on_window_resize)

    def on_commit_clicked(self, button, *args):
        """Handle commit button clicks."""
        self.commit_dialog.show_commit_confirmation()


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

    app = Adw.Application(application_id='com.kwc.Selector')
    def on_activate_with_distance(app, source_dir, selected_dir, discarded_dir):
        win = ImageSelectorWindow(source_dir, selected_dir, discarded_dir, application=app)
        win.present()
    app.connect('activate', on_activate_with_distance, source_dir, selected_dir, discarded_dir)
    app.run(None)
