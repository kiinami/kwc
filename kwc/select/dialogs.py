# Standard library imports
import re
import os
import shutil
from pathlib import Path

# Third-party imports
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Gio, Adw
from send2trash import send2trash

# Local imports
from .constants import DEFAULT_PARENT_DIRECTORY


class CommitDialog:
    """Dialog for committing selected images with metadata."""

    def __init__(self, parent_window):
        self.parent_window = parent_window

    def show_commit_confirmation(self):
        """Show confirmation dialog if there are undecided images."""
        # Find undecided images (not in selected or discarded dirs)
        undecided = [img for img in self.parent_window.source_dir.glob('*.jpg')]
        n_undecided = len(undecided)
        if n_undecided > 0:
            # Use Adw.MessageDialog for a modern modal
            msg = Adw.MessageDialog(
                transient_for=self.parent_window,
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
        """Show metadata form dialog for commit."""
        # Use Gtk.Window as an action dialog with Adw.HeaderBar
        dialog = Gtk.Window(title="Commit Metadata")
        dialog.set_transient_for(self.parent_window)
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
            self.commit_files(title, target_dir)
        commit_btn.connect("clicked", on_commit)

        dialog.present()

    def commit_files(self, title, target_dir):
        """
        Move and rename selected images to target_dir in UI order.
        Move discarded and undecided images to the system recycling bin.
        """
        # Spinner or progress UI could be added here
        selected = []
        discarded = []
        undecided = []
        for img in self.parent_window.all_images:
            if img.parent == self.parent_window.selected_dir:
                selected.append(img)
            elif img.parent == self.parent_window.discarded_dir:
                discarded.append(img)
            elif img.parent == self.parent_window.source_dir:
                undecided.append(img)
        
        # Move and rename selected images
        for idx, img in enumerate(selected, 1):
            ext = img.suffix
            new_name = f"{title}  〜 {idx:03d}{ext}"
            dest = Path(target_dir) / new_name
            try:
                shutil.move(str(img), str(dest))
            except Exception as e:
                self.show_commit_error(f"Failed to move {img.name} to {dest}: {e}")
                return
        
        # Move discarded and undecided images to trash
        for img in discarded + undecided:
            try:
                send2trash(str(img))
            except Exception as e:
                self.show_commit_error(f"Failed to move {img.name} to trash: {e}")
                return
        
        # Show completion dialog
        self.show_commit_done(len(selected), os.path.basename(target_dir))

    def show_commit_error(self, msg):
        """Show error dialog for commit failures."""
        err = Adw.MessageDialog(
            transient_for=self.parent_window,
            modal=True,
            heading="Commit Error",
            body=msg
        )
        err.add_response("ok", "OK")
        err.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
        err.set_default_response("ok")
        err.connect("response", lambda d, r: d.close())
        err.show()

    def show_commit_done(self, n, dir_name):
        """Show completion dialog after successful commit."""
        done = Adw.MessageDialog(
            transient_for=self.parent_window,
            modal=True,
            heading="Done!",
            body=f"{n} images saved in {dir_name}"
        )
        done.add_response("close", "Close")
        done.set_response_appearance("close", Adw.ResponseAppearance.SUGGESTED)
        done.set_default_response("close")
        def on_close(d, r):
            d.close()
            self.parent_window.get_application().quit()
        done.connect("response", on_close)
        done.show()
