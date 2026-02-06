"""Tests for deduplication functionality."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone
from PIL import Image

from extract.deduplication import _get_best_image, _renumber_images, process_deduplication
from extract.extractor import CancellationToken, CancelledException
from extract.models import ExtractionJob


class FakeJob:
    """Fake job for testing."""

    Status = ExtractionJob.Status

    def __init__(self, output_dir: Path, job_id: str = "test123") -> None:
        self.id = job_id
        self.output_dir = str(output_dir)
        self.params: dict[str, Any] = {
            "image_pattern": "output_{{ counter|pad:4 }}.jpg",
            "title": "Test",
            "year": "2024",
            "season": "",
            "episode": "",
        }
        self.status = ExtractionJob.Status.PENDING
        self.error = ""
        self.created_at = timezone.now()
        self.updated_at = None

    def save(self, update_fields: list[str] | None = None) -> None:
        self.updated_at = timezone.now()

    def refresh_from_db(self) -> None:
        pass


def create_test_image(path: Path, size: tuple[int, int] = (100, 100)) -> Path:
    """Create a test image file with specified dimensions."""
    img = Image.new("RGB", size, color="red")
    img.save(path)
    return path


class TestGetBestImage:
    """Test _get_best_image function."""

    def test_selects_largest_file(self, tmp_path: Path) -> None:
        """Should select the file with the largest size."""
        # Create files with different sizes
        file1 = tmp_path / "img1.jpg"
        file2 = tmp_path / "img2.jpg"
        file3 = tmp_path / "img3.jpg"

        create_test_image(file1, (50, 50))  # Smallest
        create_test_image(file2, (150, 150))  # Largest
        create_test_image(file3, (100, 100))  # Medium

        filenames = {"img1.jpg", "img2.jpg", "img3.jpg"}
        best = _get_best_image(tmp_path, filenames)

        assert best == "img2.jpg"

    def test_handles_missing_files(self, tmp_path: Path) -> None:
        """Should handle missing files gracefully."""
        file1 = tmp_path / "img1.jpg"
        create_test_image(file1, (100, 100))

        filenames = {"img1.jpg", "img2.jpg", "img3.jpg"}  # img2 and img3 don't exist
        best = _get_best_image(tmp_path, filenames)

        # Should return img1.jpg as it's the only one that exists
        assert best == "img1.jpg"

    def test_returns_first_if_all_missing(self, tmp_path: Path) -> None:
        """Should return first filename if all files are missing."""
        filenames = {"img1.jpg", "img2.jpg"}
        best = _get_best_image(tmp_path, filenames)

        # Should return one of the filenames (order is not guaranteed with sets)
        assert best in filenames

    def test_handles_single_file(self, tmp_path: Path) -> None:
        """Should handle a single file."""
        file1 = tmp_path / "img1.jpg"
        create_test_image(file1, (100, 100))

        filenames = {"img1.jpg"}
        best = _get_best_image(tmp_path, filenames)

        assert best == "img1.jpg"


class TestRenumberImages:
    """Test _renumber_images function."""

    def test_renumbers_files_sequentially(self, tmp_path: Path) -> None:
        """Should renumber files to be sequential starting from 1."""
        job = FakeJob(tmp_path)

        # Create test images with gaps in numbering
        create_test_image(tmp_path / "output_0001.jpg")
        create_test_image(tmp_path / "output_0005.jpg")
        create_test_image(tmp_path / "output_0010.jpg")

        _renumber_images(job, cancel_token=None)  # type: ignore[arg-type]

        # Should now be sequential
        assert (tmp_path / "output_0001.jpg").exists()
        assert (tmp_path / "output_0002.jpg").exists()
        assert (tmp_path / "output_0003.jpg").exists()
        assert not (tmp_path / "output_0005.jpg").exists()
        assert not (tmp_path / "output_0010.jpg").exists()

    def test_ignores_hidden_files(self, tmp_path: Path) -> None:
        """Should ignore hidden files like .cover.jpg."""
        job = FakeJob(tmp_path)

        # Create regular and hidden files
        create_test_image(tmp_path / "output_0001.jpg")
        create_test_image(tmp_path / ".cover.jpg")
        create_test_image(tmp_path / "output_0003.jpg")

        _renumber_images(job, cancel_token=None)  # type: ignore[arg-type]

        # Hidden file should remain untouched
        assert (tmp_path / ".cover.jpg").exists()
        # Regular files should be renumbered
        assert (tmp_path / "output_0001.jpg").exists()
        assert (tmp_path / "output_0002.jpg").exists()
        assert not (tmp_path / "output_0003.jpg").exists()

    def test_handles_empty_directory(self, tmp_path: Path) -> None:
        """Should handle an empty directory without errors."""
        job = FakeJob(tmp_path)
        _renumber_images(job, cancel_token=None)  # type: ignore[arg-type]  # Should not raise

    def test_respects_cancellation_token(self, tmp_path: Path) -> None:
        """Should raise CancelledException when cancelled."""
        job = FakeJob(tmp_path)
        cancel_token = CancellationToken()
        cancel_token.cancel()

        create_test_image(tmp_path / "output_0001.jpg")

        with pytest.raises(CancelledException):
            _renumber_images(job, cancel_token)  # type: ignore[arg-type]

    def test_raises_on_rename_failure(self, tmp_path: Path) -> None:
        """Should raise exception if rename fails during final stage."""
        job = FakeJob(tmp_path)
        create_test_image(tmp_path / "output_0001.jpg")

        # Mock safe_rename to fail on the second rename
        call_count = [0]

        def failing_rename(src: Path, dst: Path) -> None:
            call_count[0] += 1
            if call_count[0] > 1:  # Fail on second call (final rename)
                raise OSError("Permission denied")
            # First call (temp rename) succeeds
            src.rename(dst)

        with patch("extract.deduplication.safe_rename", side_effect=failing_rename):
            with pytest.raises(OSError, match="Permission denied"):
                _renumber_images(job, cancel_token=None)  # type: ignore[arg-type]


class TestProcessDeduplication:
    """Test process_deduplication function."""

    def test_skips_if_output_dir_missing(self, tmp_path: Path) -> None:
        """Should skip deduplication if output directory doesn't exist."""
        non_existent = tmp_path / "does_not_exist"
        job = FakeJob(non_existent)

        # Should not raise, just log warning
        process_deduplication(job, cancel_token=None)  # type: ignore[arg-type]

    def test_respects_cancellation_before_cnn_init(self, tmp_path: Path) -> None:
        """Should check cancellation before initializing CNN."""
        job = FakeJob(tmp_path)
        cancel_token = CancellationToken()
        cancel_token.cancel()

        with pytest.raises(CancelledException):
            process_deduplication(job, cancel_token)  # type: ignore[arg-type]

    def test_raises_on_cnn_initialization_failure(self, tmp_path: Path) -> None:
        """Should raise exception if CNN initialization fails."""
        job = FakeJob(tmp_path)
        create_test_image(tmp_path / "img1.jpg")

        with patch("imagededup.methods.CNN") as mock_cnn:
            mock_cnn.side_effect = RuntimeError("CNN init failed")

            with pytest.raises(RuntimeError, match="CNN init failed"):
                process_deduplication(job, cancel_token=None)  # type: ignore[arg-type]

    def test_raises_on_duplicate_processing_failure(self, tmp_path: Path) -> None:
        """Should raise exception if duplicate processing fails."""
        job = FakeJob(tmp_path)
        create_test_image(tmp_path / "img1.jpg")

        mock_cnn_instance = MagicMock()
        mock_cnn_instance.encode_images.side_effect = RuntimeError("Encoding failed")

        with patch("imagededup.methods.CNN", return_value=mock_cnn_instance):
            with pytest.raises(RuntimeError, match="Encoding failed"):
                process_deduplication(job, cancel_token=None)  # type: ignore[arg-type]

    def test_successful_deduplication(self, tmp_path: Path) -> None:
        """Should successfully identify and remove duplicates."""
        job = FakeJob(tmp_path)

        # Create test images - img1 and img2 are "duplicates", img3 is unique
        create_test_image(tmp_path / "img1.jpg", (100, 100))
        create_test_image(tmp_path / "img2.jpg", (50, 50))  # Smaller duplicate
        create_test_image(tmp_path / "img3.jpg", (120, 120))

        # Mock CNN to return duplicates
        mock_cnn_instance = MagicMock()
        mock_cnn_instance.encode_images.return_value = {
            "img1.jpg": "encoding1",
            "img2.jpg": "encoding2",
            "img3.jpg": "encoding3",
        }
        mock_cnn_instance.find_duplicates.return_value = {
            "img1.jpg": ["img2.jpg"],  # img1 and img2 are duplicates
            "img2.jpg": ["img1.jpg"],
            "img3.jpg": [],  # img3 is unique
        }

        with patch("imagededup.methods.CNN", return_value=mock_cnn_instance):
            process_deduplication(job, cancel_token=None, threshold=0.9)  # type: ignore[arg-type]

        # After deduplication and renumbering:
        # - img2 (smaller) should be deleted
        # - Remaining files (img1.jpg, img3.jpg) should be renumbered sequentially
        # - Since files are sorted alphabetically, img1.jpg becomes output_0001.jpg and img3.jpg becomes output_0002.jpg
        assert not (tmp_path / "img2.jpg").exists()  # img2 should be deleted
        assert (tmp_path / "output_0001.jpg").exists()  # Renumbered from img1.jpg
        assert (tmp_path / "output_0002.jpg").exists()  # Renumbered from img3.jpg

        # Original filenames should not exist after renumbering
        assert not (tmp_path / "img1.jpg").exists()
        assert not (tmp_path / "img3.jpg").exists()

    def test_no_duplicates_found(self, tmp_path: Path) -> None:
        """Should handle case where no duplicates are found."""
        job = FakeJob(tmp_path)

        create_test_image(tmp_path / "img1.jpg")
        create_test_image(tmp_path / "img2.jpg")

        # Mock CNN to return no duplicates
        mock_cnn_instance = MagicMock()
        mock_cnn_instance.encode_images.return_value = {
            "img1.jpg": "encoding1",
            "img2.jpg": "encoding2",
        }
        mock_cnn_instance.find_duplicates.return_value = {
            "img1.jpg": [],
            "img2.jpg": [],
        }

        with patch("imagededup.methods.CNN", return_value=mock_cnn_instance):
            process_deduplication(job, cancel_token=None, threshold=0.9)  # type: ignore[arg-type]

        # All files should remain
        assert (tmp_path / "img1.jpg").exists()
        assert (tmp_path / "img2.jpg").exists()

    def test_respects_cancellation_during_processing(self, tmp_path: Path) -> None:
        """Should respect cancellation token during duplicate processing."""
        job = FakeJob(tmp_path)
        create_test_image(tmp_path / "img1.jpg")

        cancel_token = CancellationToken()

        # Mock CNN to succeed encoding but trigger cancellation
        mock_cnn_instance = MagicMock()
        mock_cnn_instance.encode_images.return_value = {"img1.jpg": "encoding1"}

        def cancel_after_encoding(*args, **kwargs):
            cancel_token.cancel()
            return {"img1.jpg": []}

        mock_cnn_instance.find_duplicates.side_effect = cancel_after_encoding

        with patch("imagededup.methods.CNN", return_value=mock_cnn_instance):
            with pytest.raises(CancelledException):
                process_deduplication(job, cancel_token, threshold=0.9)  # type: ignore[arg-type]

    def test_uses_custom_threshold(self, tmp_path: Path) -> None:
        """Should pass custom threshold to CNN."""
        job = FakeJob(tmp_path)
        create_test_image(tmp_path / "img1.jpg")

        mock_cnn_instance = MagicMock()
        mock_cnn_instance.encode_images.return_value = {"img1.jpg": "encoding1"}
        mock_cnn_instance.find_duplicates.return_value = {"img1.jpg": []}

        with patch("imagededup.methods.CNN", return_value=mock_cnn_instance):
            process_deduplication(job, cancel_token=None, threshold=0.95)  # type: ignore[arg-type]

        # Verify threshold was passed correctly
        mock_cnn_instance.find_duplicates.assert_called_once()
        call_kwargs = mock_cnn_instance.find_duplicates.call_args[1]
        assert call_kwargs["min_similarity_threshold"] == 0.95

    def test_environment_initialization(self, tmp_path: Path) -> None:
        """Should initialize environment variables for CNN."""
        job = FakeJob(tmp_path)
        create_test_image(tmp_path / "img1.jpg")

        import os

        # Clear env vars to test initialization
        env_before = os.environ.copy()
        for key in ["USER", "TORCH_HOME", "XDG_CACHE_HOME"]:
            os.environ.pop(key, None)

        mock_cnn_instance = MagicMock()
        mock_cnn_instance.encode_images.return_value = {"img1.jpg": "encoding1"}
        mock_cnn_instance.find_duplicates.return_value = {"img1.jpg": []}

        with patch("imagededup.methods.CNN", return_value=mock_cnn_instance):
            process_deduplication(job, cancel_token=None)  # type: ignore[arg-type]

        # Check that environment variables were set
        assert "USER" in os.environ
        assert "TORCH_HOME" in os.environ
        assert "XDG_CACHE_HOME" in os.environ
        assert tempfile.gettempdir() in os.environ["TORCH_HOME"]
        assert tempfile.gettempdir() in os.environ["XDG_CACHE_HOME"]

        # Restore original environment
        os.environ.clear()
        os.environ.update(env_before)
