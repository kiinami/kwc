"""
Image management model for KWC Selector.

This module handles all business logic related to image operations,
file management, and state tracking.
"""

import shutil
from pathlib import Path
from typing import List, Optional, Tuple, Callable
from send2trash import send2trash


class ImageManager:
    """Manages image collections and operations."""

    def __init__(self, source_dir: Path, selected_dir: Path, discarded_dir: Path):
        """
        Initialize the image manager.
        
        Args:
            source_dir: Directory containing source images
            selected_dir: Directory for selected/kept images
            discarded_dir: Directory for discarded images
        """
        self.source_dir = source_dir
        self.selected_dir = selected_dir
        self.discarded_dir = discarded_dir
        
        # Image collection and state
        self._all_images: List[Path] = []
        self._current_index: int = 0
        self._undo_stack: List[Tuple[Path, Path, int]] = []
        
        # Event callbacks
        self._on_image_moved: Optional[Callable[[Path, Path], None]] = None
        self._on_index_changed: Optional[Callable[[int], None]] = None
        
        self._load_images()

    def _load_images(self) -> None:
        """Load all images from the three directories, sorted by numeric suffix."""
        all_images = (
            list(self.source_dir.glob('*.jpg')) +
            list(self.selected_dir.glob('*.jpg')) +
            list(self.discarded_dir.glob('*.jpg'))
        )
        
        # Sort by numeric suffix (e.g., output_0001.jpg -> 1)
        def sort_key(path: Path) -> int:
            try:
                return int(path.stem.split('_')[-1])
            except (ValueError, IndexError):
                return 0
        
        self._all_images = sorted(all_images, key=sort_key)

    @property
    def all_images(self) -> List[Path]:
        """Get all images in the collection."""
        return self._all_images.copy()

    @property
    def current_index(self) -> int:
        """Get the current image index."""
        return self._current_index

    @property
    def current_image(self) -> Optional[Path]:
        """Get the currently selected image."""
        if 0 <= self._current_index < len(self._all_images):
            return self._all_images[self._current_index]
        return None

    @property
    def total_images(self) -> int:
        """Get total number of images."""
        return len(self._all_images)

    @property
    def classification_progress(self) -> Tuple[int, int]:
        """
        Get classification progress.
        
        Returns:
            Tuple of (classified_count, total_count)
        """
        classified = sum(
            1 for img in self._all_images
            if img.parent in [self.selected_dir, self.discarded_dir]
        )
        return classified, len(self._all_images)

    def set_current_index(self, index: int) -> bool:
        """
        Set the current image index.
        
        Args:
            index: The new index to set
            
        Returns:
            True if index was changed, False otherwise
        """
        if not (0 <= index < len(self._all_images)):
            return False
            
        if index != self._current_index:
            self._current_index = index
            if self._on_index_changed:
                self._on_index_changed(index)
        return True

    def navigate_to_next(self) -> bool:
        """Navigate to next image."""
        return self.set_current_index(min(len(self._all_images) - 1, self._current_index + 1))

    def navigate_to_previous(self) -> bool:
        """Navigate to previous image."""
        return self.set_current_index(max(0, self._current_index - 1))

    def find_initial_selection_index(self) -> int:
        """Find the best initial image index (preferring source directory)."""
        for i, img in enumerate(self._all_images):
            if img.parent == self.source_dir:
                return i
        return 0 if self._all_images else 0

    def find_next_unclassified_index(self, start_idx: Optional[int] = None) -> Optional[int]:
        """
        Find the next unclassified image index.
        
        Args:
            start_idx: Index to start searching from (default: current_index + 1)
            
        Returns:
            Next unclassified image index, or None if none found
        """
        if start_idx is None:
            start_idx = self._current_index + 1
            
        for i in range(start_idx, len(self._all_images)):
            if self._all_images[i].parent == self.source_dir:
                return i
        return None

    def move_image_to_directory(self, target_dir: Path, image_index: Optional[int] = None) -> bool:
        """
        Move an image to a target directory.
        
        Args:
            target_dir: Directory to move the image to
            image_index: Index of image to move (default: current image)
            
        Returns:
            True if successful, False otherwise
        """
        if image_index is None:
            image_index = self._current_index
            
        if not (0 <= image_index < len(self._all_images)):
            return False
            
        source_path = self._all_images[image_index]
        
        # Don't move if already in target directory
        if source_path.parent == target_dir:
            return True
            
        dest_path = target_dir / source_path.name
        
        try:
            # Record for undo before moving
            self._undo_stack.append((source_path, dest_path, image_index))
            
            # Move the file
            source_path.rename(dest_path)
            
            # Update the image list
            self._all_images[image_index] = dest_path
            
            # Notify listeners
            if self._on_image_moved:
                self._on_image_moved(source_path, dest_path)
                
            return True
            
        except Exception as e:
            # Remove from undo stack if move failed
            if self._undo_stack and self._undo_stack[-1][2] == image_index:
                self._undo_stack.pop()
            print(f"Error moving {source_path} to {dest_path}: {e}")
            return False

    def keep_current_image(self) -> bool:
        """Move current image to selected directory."""
        return self.move_image_to_directory(self.selected_dir)

    def discard_current_image(self) -> bool:
        """Move current image to discarded directory."""
        return self.move_image_to_directory(self.discarded_dir)

    def undo_last_action(self) -> bool:
        """
        Undo the last image move action.
        
        Returns:
            True if successful, False otherwise
        """
        if not self._undo_stack:
            return False
            
        source_path, dest_path, image_index = self._undo_stack.pop()
        
        try:
            if dest_path.exists():
                dest_path.rename(source_path)
                self._all_images[image_index] = source_path
                
                # Notify listeners
                if self._on_image_moved:
                    self._on_image_moved(dest_path, source_path)
                    
                return True
        except Exception as e:
            print(f"Error undoing move from {dest_path} to {source_path}: {e}")
            
        return False

    def get_images_by_category(self) -> Tuple[List[Path], List[Path], List[Path]]:
        """
        Get images categorized by their current location.
        
        Returns:
            Tuple of (selected_images, discarded_images, undecided_images)
        """
        selected = []
        discarded = []
        undecided = []
        
        for img in self._all_images:
            if img.parent == self.selected_dir:
                selected.append(img)
            elif img.parent == self.discarded_dir:
                discarded.append(img)
            elif img.parent == self.source_dir:
                undecided.append(img)
                
        return selected, discarded, undecided

    def commit_images(self, target_dir: Path, title: str) -> bool:
        """
        Commit selected images to target directory and trash the rest.
        
        Args:
            target_dir: Directory to save selected images to
            title: Title to use for image naming
            
        Returns:
            True if successful, False otherwise
        """
        selected, discarded, undecided = self.get_images_by_category()
        
        try:
            # Move and rename selected images
            for idx, img in enumerate(selected, 1):
                ext = img.suffix
                new_name = f"{title}  〜 {idx:03d}{ext}"
                dest = target_dir / new_name
                shutil.move(str(img), str(dest))
            
            # Move discarded and undecided images to trash
            for img in discarded + undecided:
                send2trash(str(img))
                
            return True
            
        except Exception as e:
            print(f"Error during commit: {e}")
            return False

    def set_image_moved_callback(self, callback: Callable[[Path, Path], None]) -> None:
        """Set callback for when images are moved."""
        self._on_image_moved = callback

    def set_index_changed_callback(self, callback: Callable[[int], None]) -> None:
        """Set callback for when current index changes."""
        self._on_index_changed = callback
