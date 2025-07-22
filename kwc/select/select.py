# Standard library imports
import time
from pathlib import Path

# Third-party imports
from PIL import Image, ExifTags
import gi
# Specify required versions before importing Gtk and Adw
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Gdk, GObject, Gio, Adw

# Local imports
from .utils import get_or_compute_hash, get_all_images
from .widgets import LazyThumbnailButton
from .constants import (
    THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT, CROSSFADE_DURATION, SCROLL_ANIMATION_DURATION,
    SCROLL_ANIMATION_STEPS, LAZY_LOAD_BUFFER, HASH_EXIF_TAG, HASH_EXIF_PREFIX
)
from .style import load_css

# CSS loading
load_css()


class ImageSelectorWindow(Adw.ApplicationWindow):
    """Main window for the image selector application (Adwaita style)."""

    def __init__(self, source_dir: Path, selected_dir: Path, discarded_dir: Path, hash_group_distance: int = 5, **kwargs):
        super().__init__(**kwargs, title='KWC Selector')
        # State variables
        self.source_dir: Path = source_dir
        self.selected_dir: Path = selected_dir
        self.discarded_dir: Path = discarded_dir
        self.hash_group_distance: int = hash_group_distance
        self.current_index: int = 0  # Index of the currently displayed image
        self.picture_path: Path | None = None  # Path of the current image
        self.thumb_buttons: list = []  # List of thumbnail button widgets
        self.undo_stack: list = []  # Stack of (src, dest, index) for undo

        self._init_header_bar()
        self._init_main_layout()
        self._setup_ui()
        self._setup_images()
        # self._setup_event_handlers()  # <-- Remove from here
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

        # Create a loading group (centered vbox) for progress bar and label
        self.loading_group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.loading_group.set_halign(Gtk.Align.CENTER)
        self.loading_group.set_valign(Gtk.Align.CENTER)
        self.loading_group.set_vexpand(True)
        self.loading_group.set_hexpand(True)
        self.loading_group.set_margin_top(0)
        self.loading_group.set_margin_bottom(0)
        self.loading_group.set_margin_start(0)
        self.loading_group.set_margin_end(0)
        self.progress_label = Gtk.Label(label="Loading images… 0 of 0")
        self.progress_label.set_justify(Gtk.Justification.CENTER)
        self.progress_label.set_halign(Gtk.Align.CENTER)
        self.progress_label.set_valign(Gtk.Align.CENTER)
        self.progress_label.set_margin_bottom(8)
        self.progress_label.add_css_class("progress-label-large")
        self.loading_group.append(self.progress_label)
        self.progressbar = Gtk.ProgressBar()
        self.progressbar.set_hexpand(True)
        self.progressbar.set_halign(Gtk.Align.CENTER)
        self.progressbar.set_valign(Gtk.Align.CENTER)
        self.progressbar.set_margin_top(0)
        self.progressbar.set_margin_bottom(0)
        self.progressbar.set_show_text(False)
        self.progressbar.set_fraction(0.0)
        self.progressbar.set_size_request(600, -1)  # Max width, let theme handle height
        self.loading_group.append(self.progressbar)
        self._main_vbox.append(self.loading_group)
        self.loading_group.show()

    def _setup_ui(self):
        """Set up the main UI containers and widgets."""
        # Only set up the rest of the UI after loading is complete
        pass

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

    def _create_main_container(self) -> Gtk.Box:
        """Create and configure the main container box (Adwaita style)."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)
        box.add_css_class("boxed-list")
        return box

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

    def _create_action_buttons(self) -> Gtk.Box:
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
        """Show and update the progress bar and label."""
        self.loading_group.set_visible(True)
        total = len(self.all_images)
        current = getattr(self, '_hash_index', 0)
        self.progressbar.set_fraction(fraction)
        self.progress_label.set_text(f"Loading images… {current} of {total}")
        self.progress_label.set_visible(True)
        self.progressbar.remove_css_class("fade-out")

    def _hide_progress(self):
        """Fade out and hide the progress bar overlay, then show main UI."""
        def on_fade_out(*_):
            self.loading_group.set_visible(False)
            self._setup_main_ui_after_loading()
        self.progressbar.add_css_class("fade-out")
        from gi.repository import GObject
        GObject.timeout_add(400, on_fade_out)

    def _setup_main_ui_after_loading(self):
        """Show the main UI after loading is complete."""
        # Main image area
        self._create_image_stack()
        self.picture_stack.set_vexpand(True)
        self._main_vbox.append(self.picture_stack)

        # Action buttons (Keep/Discard)
        self._main_vbox.append(self._create_action_buttons())

        # Filmstrip
        self._create_filmstrip()
        self._main_vbox.append(self.filmstrip_scroller)
        self._setup_event_handlers()
        # Now that filmstrip UI exists, populate it
        self.populate_filmstrip()
        self.set_initial_selection()

    def update_progress_label(self, current, total):
        """Update the progress label text."""
        self.progress_label.set_text(f"Loading images… {current} of {total}")

    def _ensure_hashes_with_progress(self):
        """Compute hashes for all images, updating the progress bar asynchronously."""
        from gi.repository import GLib
        total = len(self.all_images)
        if total == 0:
            self._hide_progress()
            return
        self.loading_group.set_visible(True)
        self.progressbar.set_fraction(0.0)
        self.progress_label.set_text("Loading images… 0 of {}".format(total))
        self.progress_label.set_visible(True)
        self._hash_index = 0
        def process_next():
            if self._hash_index >= total:
                self._hide_progress()
                return False  # Stop the idle handler
            img = self.all_images[self._hash_index]
            self.image_hashes[img] = get_or_compute_hash(img)
            self._hash_index += 1
            fraction = self._hash_index / total
            self._show_progress(fraction)
            return True  # Continue processing
        GLib.idle_add(process_next)

    def _create_filmstrip(self):
        """Create the filmstrip thumbnail viewer."""
        self.filmstrip_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.filmstrip_box.set_valign(Gtk.Align.CENTER)

        self.filmstrip_scroller = Gtk.ScrolledWindow()
        self.filmstrip_scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.filmstrip_scroller.add_css_class("filmstrip-scroller")
        self.filmstrip_scroller.set_child(self.filmstrip_box)
        self.filmstrip_scroller.set_min_content_height(100)

    def _setup_images(self):
        """Set up image list and start hash computation with progress."""
        self.all_images = get_all_images(self.source_dir, self.selected_dir, self.discarded_dir)
        self.image_hashes = {}
        self._ensure_hashes_with_progress()

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
            button.add_css_class("thumb-selected")
        elif img.parent == self.discarded_dir:
            button.add_css_class("thumb-discarded")
        return button

    def populate_filmstrip(self):
        """Populate the filmstrip with thumbnail buttons."""
        self._clear_filmstrip()
        self.thumb_buttons = []
        for idx, img in enumerate(self.all_images):
            button = self._create_thumbnail_button(img, idx)
            self.filmstrip_box.append(button)
            self.thumb_buttons.append(button)
        GObject.idle_add(self.load_visible_thumbnails)
        self.update_header_title()

    def set_initial_selection(self):
        """Set the initial image selection, preferring images from source directory."""
        for i, img in enumerate(self.all_images):
            if img.parent == self.source_dir:
                self._navigate_to_image(i)
                return
        # Fallback to first image if no source images found
        if self.all_images:
            self._navigate_to_image(0)

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

    def on_thumbnail_clicked(self, button, idx):
        """Handle thumbnail button clicks."""
        self._navigate_to_image(idx)

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
            self._update_button_styles(new_index)
            self._update_action_button_styles(self.picture_path)
            self.center_filmstrip_on_selected(new_index)
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
            self._update_button_styles(self.current_index)
            self._update_action_button_styles(self.picture_path)
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
                self._update_button_styles(idx)
                self._update_action_button_styles(src)
                self.update_header_title()
        except Exception as e:
            print(f"Error undoing move from {dest} to {src}: {e}")

    def _update_button_styles(self, current_idx):
        for idx, button in enumerate(self.thumb_buttons):
            button.remove_css_class("current-thumb")
            if idx == current_idx:
                button.add_css_class("current-thumb")
            # Update selected/discarded styles
            button.remove_css_class("thumb-selected")
            button.remove_css_class("thumb-discarded")
            img = self.all_images[idx]
            if img.parent == self.selected_dir:
                button.add_css_class("thumb-selected")
            elif img.parent == self.discarded_dir:
                button.add_css_class("thumb-discarded")

    def _update_action_button_styles(self, image_path):
        # Optionally update action button states (e.g., disable if already in that dir)
        if image_path.parent == self.selected_dir:
            self.keep_button.set_sensitive(False)
            self.discard_button.set_sensitive(True)
        elif image_path.parent == self.discarded_dir:
            self.keep_button.set_sensitive(True)
            self.discard_button.set_sensitive(False)
        else:
            self.keep_button.set_sensitive(True)
            self.discard_button.set_sensitive(True)

    def on_key_press_event(self, controller, keyval, keycode, state, *args):
        # Handle key events for navigation and actions
        if keyval == Gdk.KEY_q:
            self.on_keep()
            return True
        elif keyval == Gdk.KEY_w:
            self.on_discard()
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

    def on_keep(self):
        if self.picture_path.parent != self.selected_dir:
            self._move_image_to_directory(self.selected_dir)
            next_idx = self._find_next_unclassified_index()
            if next_idx is not None:
                self._navigate_to_image(next_idx)

    def on_discard(self):
        if self.picture_path.parent != self.discarded_dir:
            self._move_image_to_directory(self.discarded_dir)
            next_idx = self._find_next_unclassified_index()
            if next_idx is not None:
                self._navigate_to_image(next_idx)

    def on_filmstrip_scroll(self, controller, dx, dy):
        # Optionally handle scroll events for navigation
        if dy < 0:
            self._navigate_to_image(max(0, self.current_index - 1))
        elif dy > 0:
            self._navigate_to_image(min(len(self.all_images) - 1, self.current_index + 1))
        return True

    def on_scroll_value_changed(self, adjustment):
        GObject.idle_add(self.load_visible_thumbnails)

    def animate_image_transition(self, new_image_path):
        # Optionally implement crossfade or other animation
        pass

    def on_window_resize(self, widget, param):
        GObject.idle_add(self.load_visible_thumbnails)

    def on_scroller_focus_change(self, controller, *args):
        GObject.idle_add(self.load_visible_thumbnails)

    def delayed_initial_load(self):
        GObject.idle_add(self.load_visible_thumbnails)

    def _setup_event_handlers(self):
        # Connect scroll and resize events
        scroll_controller = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll_controller.connect('scroll', self.on_filmstrip_scroll)
        self.filmstrip_scroller.add_controller(scroll_controller)
        hadj = self.filmstrip_scroller.get_hadjustment()
        hadj.connect('value-changed', self.on_scroll_value_changed)
        self._main_vbox.connect('notify::allocation', self.on_window_resize)
        focus_controller = Gtk.EventControllerFocus()
        focus_controller.connect('enter', self.on_scroller_focus_change)
        self.filmstrip_scroller.add_controller(focus_controller)

    def on_commit_clicked(self, button, *args):
        # Find undecided images (not in selected or discarded dirs)
        undecided = [img for img in self.source_dir.glob('*.jpg')]
        n_undecided = len(undecided)
        if n_undecided > 0:
            # Use Adw.MessageDialog for a modern modal
            msg = Adw.MessageDialog(
                transient_for=self,
                modal=True,
                heading="Undecided Images Warning",
                body=f"There are still {n_undecided} images that have not been classified.\nIf you continue, they will be discarded."
            )
            msg.set_size_request(350, -1)  # Set minimum width
            msg.add_response("go-back", "Go Back")
            msg.add_response("continue", "Continue")
            msg.set_response_appearance("continue", Adw.ResponseAppearance.SUGGESTED)
            msg.set_default_response("continue")
            def on_response(dialog, response):
                dialog.hide()
                dialog.destroy()
                if response == "continue":
                    self.show_metadata_form()
                else:
                    print("User chose to go back from undecided warning dialog.")
            msg.connect("response", on_response)
            msg.show()
        else:
            self.show_metadata_form()

    def show_metadata_form(self):
        from .constants import DEFAULT_PARENT_DIRECTORY
        import re
        import os
        # Use Gtk.Window as an action dialog with Adw.HeaderBar
        dialog = Gtk.Window(title="Commit Metadata")
        dialog.set_transient_for(self)
        dialog.set_modal(True)
        dialog.set_resizable(False)
        dialog.set_default_size(440, 320)
        dialog.set_deletable(False)  # Hide the close window button
        # Header bar with Cancel (left) and Commit (right)
        header = Adw.HeaderBar()
        header.title = "Commit Metadata"  # Use title property for consistency
        # Cancel button (left)
        cancel_btn = Gtk.Button.new_with_label("Cancel")
        header.pack_start(cancel_btn)
        # Commit button (right)
        commit_btn = Gtk.Button.new_with_label("Commit")
        commit_btn.get_style_context().add_class("suggested-action")
        commit_btn.set_sensitive(False)
        header.pack_end(commit_btn)
        dialog.set_titlebar(header)
        # Main content
        clamp = Adw.Clamp()
        clamp.set_maximum_size(480)
        clamp.set_margin_top(24)
        clamp.set_margin_bottom(24)
        clamp.set_margin_start(24)
        clamp.set_margin_end(24)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        # Title
        title_row = Adw.EntryRow()
        title_row.set_title("Title")
        # Release year
        year_row = Adw.EntryRow()
        year_row.set_title("Release Year")
        year_row.set_max_length(4)
        # End year
        end_row = Adw.EntryRow()
        end_row.set_title("End Year (optional)")
        end_row.set_max_length(4)
        # Parent directory chooser
        dir_row = Adw.ActionRow()
        dir_row.set_title("Parent Directory")
        dir_label = Gtk.Label(label=str(DEFAULT_PARENT_DIRECTORY))
        dir_label.set_halign(Gtk.Align.START)
        dir_label.set_hexpand(True)
        dir_button = Gtk.Button.new_with_label("Choose…")
        dir_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        dir_hbox.append(dir_label)
        dir_hbox.append(dir_button)
        dir_row.set_child(dir_hbox)
        # Add all rows to vbox
        vbox.append(title_row)
        vbox.append(year_row)
        vbox.append(end_row)
        vbox.append(dir_row)
        clamp.set_child(vbox)
        dialog.set_child(clamp)

        # Helper: validate and build directory name
        def build_dir_name(title, year, end_year):
            # Remove leading/trailing whitespace
            title = title.strip()
            year = year.strip()
            end_year = end_year.strip()
            # Series if end_year is filled
            if end_year:
                return f"{title} ({year} - {end_year})"
            else:
                return f"{title} ({year})"

        # Helper: show error dialog
        def show_error(msg):
            err = Adw.MessageDialog(
                transient_for=dialog,
                modal=True,
                heading="Error",
                body=msg
            )
            err.add_response("ok", "OK")
            err.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
            err.set_default_response("ok")
            err.connect("response", lambda d, r: d.close())
            err.show()

        # Directory chooser logic
        def on_choose_dir(_btn):
            file_chooser = Gtk.FileChooserNative(
                title="Select Parent Directory",
                transient_for=dialog,
                action=Gtk.FileChooserAction.SELECT_FOLDER
            )
            file_chooser.set_current_folder(Gio.File.new_for_path(str(DEFAULT_PARENT_DIRECTORY)))
            def on_response(fc, resp):
                if resp == Gtk.ResponseType.ACCEPT:
                    chosen = fc.get_file().get_path()
                    dir_label.set_text(chosen)
                fc.destroy()
            file_chooser.connect("response", on_response)
            file_chooser.show()
        dir_button.connect("clicked", on_choose_dir)

        # Enable/disable commit button based on validation
        def validate_fields(_row=None):
            title = title_row.get_text().strip()
            year = year_row.get_text().strip()
            end_year = end_row.get_text().strip()
            parent_dir = dir_label.get_text().strip()
            valid = bool(title) and year.isdigit() and len(year) == 4
            if end_year:
                valid = valid and end_year.isdigit() and len(end_year) == 4 and int(end_year) >= int(year)
            # Block invalid filesystem characters
            invalid_fs = r'[\\/:*?"<>|]'
            if re.search(invalid_fs, title) or re.search(invalid_fs, year) or (end_year and re.search(invalid_fs, end_year)):
                valid = False
            commit_btn.set_sensitive(valid)
        title_row.connect("changed", validate_fields)
        year_row.connect("changed", validate_fields)
        end_row.connect("changed", validate_fields)

        # Cancel button closes dialog
        cancel_btn.connect("clicked", lambda *_: dialog.close())

        # Commit button logic
        def on_commit(_btn):
            title = title_row.get_text().strip()
            year = year_row.get_text().strip()
            end_year = end_row.get_text().strip()
            parent_dir = dir_label.get_text().strip()
            dir_name = build_dir_name(title, year, end_year)
            target_dir = os.path.join(parent_dir, dir_name)
            if os.path.exists(target_dir):
                show_error(f"The directory '{dir_name}' already exists in the selected location.")
                return
            try:
                os.makedirs(target_dir)
            except Exception as e:
                show_error(f"Failed to create directory: {e}")
                return
            dialog.close()
            self._commit_files(title, target_dir)
        commit_btn.connect("clicked", on_commit)

        dialog.present()

    def _commit_files(self, title, target_dir):
        """
        Move and rename selected images to target_dir in UI order.
        Move discarded and undecided images to the system recycling bin.
        """
        import shutil
        from send2trash import send2trash
        from pathlib import Path
        import os
        # Spinner or progress UI could be added here
        selected = []
        discarded = []
        undecided = []
        for img in self.all_images:
            if img.parent == self.selected_dir:
                selected.append(img)
            elif img.parent == self.discarded_dir:
                discarded.append(img)
            elif img.parent == self.source_dir:
                undecided.append(img)
        # Move and rename selected images
        for idx, img in enumerate(selected, 1):
            ext = img.suffix
            new_name = f"{title}  〜 {idx:03d}{ext}"
            dest = Path(target_dir) / new_name
            try:
                shutil.move(str(img), str(dest))
            except Exception as e:
                self._show_commit_error(f"Failed to move {img.name} to {dest}: {e}")
                return
        # Move discarded and undecided images to trash
        for img in discarded + undecided:
            try:
                send2trash(str(img))
            except Exception as e:
                self._show_commit_error(f"Failed to move {img.name} to trash: {e}")
                return
        # Show completion dialog
        self._show_commit_done(len(selected), os.path.basename(target_dir))

    def _show_commit_error(self, msg):
        err = Adw.MessageDialog(
            transient_for=self,
            modal=True,
            heading="Commit Error",
            body=msg
        )
        err.add_response("ok", "OK")
        err.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
        err.set_default_response("ok")
        err.connect("response", lambda d, r: d.close())
        err.show()

    def _show_commit_done(self, n, dir_name):
        done = Adw.MessageDialog(
            transient_for=self,
            modal=True,
            heading="Done!",
            body=f"{n} images saved in {dir_name}"
        )
        done.add_response("close", "Close")
        done.set_response_appearance("close", Adw.ResponseAppearance.SUGGESTED)
        done.set_default_response("close")
        def on_close(d, r):
            d.close()
            self.get_application().quit()
        done.connect("response", on_close)
        done.show()
def select(source_dir: Path, selected_dir: Path, discarded_dir: Path, hash_group_distance: int = 5):
    """
    Main entry point for the image selector application.

    Args:
        source_dir: Directory containing source images
        selected_dir: Directory for selected/kept images
        discarded_dir: Directory for discarded images
        hash_group_distance: Perceptual hash distance threshold for grouping (ignored)
    """
    # Ensure target directories exist
    selected_dir.mkdir(exist_ok=True)
    discarded_dir.mkdir(exist_ok=True)

    app = Adw.Application(application_id='com.kwc.Selector')
    def on_activate_with_distance(app, source_dir, selected_dir, discarded_dir, hash_group_distance):
        win = ImageSelectorWindow(source_dir, selected_dir, discarded_dir, hash_group_distance, application=app)
        win.present()
    app.connect('activate', on_activate_with_distance, source_dir, selected_dir, discarded_dir, hash_group_distance)
    app.run(None)
