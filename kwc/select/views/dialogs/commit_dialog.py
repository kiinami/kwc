"""
Commit dialog for saving selected images.

This module contains dialog components for the commit functionality.
"""

import os
import re
from pathlib import Path
from typing import Optional, Callable

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Gio, Adw

from ...models.image_manager import ImageManager
from ...utils.constants import DEFAULT_PARENT_DIRECTORY


class CommitDialog:
    """Dialog for committing selected images with metadata."""

    def __init__(self, parent_window: Gtk.Window, image_manager: ImageManager,
                 on_commit_complete: Optional[Callable[[], None]] = None):
        """
        Initialize the commit dialog.
        
        Args:
            parent_window: Parent window for the dialog
            image_manager: Image manager model
            on_commit_complete: Callback for when commit is completed
        """
        self.parent_window = parent_window
        self.image_manager = image_manager
        self._on_commit_complete = on_commit_complete

    def show_commit_confirmation(self) -> None:
        """Show confirmation dialog if there are undecided images."""
        selected, discarded, undecided = self.image_manager.get_images_by_category()
        
        if undecided:
            self._show_undecided_warning(len(undecided))
        else:
            self._show_metadata_form()

    def _show_undecided_warning(self, n_undecided: int) -> None:
        """Show warning dialog about undecided images."""
        msg = Adw.MessageDialog(
            transient_for=self.parent_window,
            modal=True,
            heading="Undecided Images Warning",
            body=f"There are still {n_undecided} images that have not been classified.\n"
                 f"If you continue, they will be discarded."
        )
        msg.set_size_request(350, -1)
        msg.add_response("go-back", "Go Back")
        msg.add_response("continue", "Continue")
        msg.set_response_appearance("continue", Adw.ResponseAppearance.SUGGESTED)
        msg.set_default_response("continue")
        
        def on_response(dialog, response):
            dialog.close()
            if response == "continue":
                self._show_metadata_form()
        
        msg.connect("response", on_response)
        msg.show()

    def _show_metadata_form(self) -> None:
        """Show metadata form dialog for commit."""
        dialog = Gtk.Window(title="Commit Metadata")
        dialog.set_transient_for(self.parent_window)
        dialog.set_modal(True)
        dialog.set_resizable(False)
        dialog.set_default_size(440, 320)
        dialog.set_deletable(False)
        
        # Create header bar
        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Label(label="Commit Metadata"))
        
        # Cancel button
        cancel_btn = Gtk.Button.new_with_label("Cancel")
        header.pack_start(cancel_btn)
        
        # Commit button
        commit_btn = Gtk.Button.new_with_label("Commit")
        commit_btn.add_css_class("suggested-action")
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
        
        # Title entry
        title_row = Adw.EntryRow()
        title_row.set_title("Title")
        
        # Release year entry
        year_row = Adw.EntryRow()
        year_row.set_title("Release Year")
        year_row.set_max_length(4)
        
        # End year entry
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

        # Helper functions
        def build_dir_name(title: str, year: str, end_year: str) -> str:
            """Build directory name from metadata."""
            title = title.strip()
            year = year.strip()
            end_year = end_year.strip()
            
            if end_year:
                return f"{title} ({year} - {end_year})"
            else:
                return f"{title} ({year})"

        def validate_fields() -> None:
            """Validate form fields and enable/disable commit button."""
            title = title_row.get_text().strip()
            year = year_row.get_text().strip()
            end_year = end_row.get_text().strip()
            
            valid = bool(title) and year.isdigit() and len(year) == 4
            
            if end_year:
                valid = valid and end_year.isdigit() and len(end_year) == 4 and int(end_year) >= int(year)
            
            # Check for invalid filesystem characters
            invalid_fs = r'[\\/:*?"<>|]'
            if re.search(invalid_fs, title) or re.search(invalid_fs, year) or (end_year and re.search(invalid_fs, end_year)):
                valid = False
                
            commit_btn.set_sensitive(valid)

        def show_error(msg: str) -> None:
            """Show error dialog."""
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

        def on_choose_dir(_btn):
            """Handle directory chooser button."""
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

        def on_commit(_btn):
            """Handle commit button click."""
            title = title_row.get_text().strip()
            year = year_row.get_text().strip()
            end_year = end_row.get_text().strip()
            parent_dir = dir_label.get_text().strip()
            
            dir_name = build_dir_name(title, year, end_year)
            target_dir = Path(parent_dir) / dir_name
            
            if target_dir.exists():
                show_error(f"The directory '{dir_name}' already exists in the selected location.")
                return
                
            try:
                target_dir.mkdir(parents=True)
                dialog.close()
                self._commit_files(title, target_dir)
            except Exception as e:
                show_error(f"Failed to create directory: {e}")

        # Connect events
        title_row.connect("changed", lambda *_: validate_fields())
        year_row.connect("changed", lambda *_: validate_fields())
        end_row.connect("changed", lambda *_: validate_fields())
        dir_button.connect("clicked", on_choose_dir)
        cancel_btn.connect("clicked", lambda *_: dialog.close())
        commit_btn.connect("clicked", on_commit)

        dialog.present()

    def _commit_files(self, title: str, target_dir: Path) -> None:
        """Execute the file commit operation."""
        try:
            if self.image_manager.commit_images(target_dir, title):
                selected, _, _ = self.image_manager.get_images_by_category()
                self._show_commit_done(len(selected), target_dir.name)
            else:
                self._show_commit_error("Failed to commit images")
        except Exception as e:
            self._show_commit_error(f"Commit error: {e}")

    def _show_commit_error(self, msg: str) -> None:
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

    def _show_commit_done(self, n: int, dir_name: str) -> None:
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
            if self._on_commit_complete:
                self._on_commit_complete()
        
        done.connect("response", on_close)
        done.show()
