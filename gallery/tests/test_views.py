"""Tests for gallery views."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from PIL import Image


pytestmark = pytest.mark.django_db(transaction=True)


class GalleryViewsTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp_dir = Path(tempfile.mkdtemp(prefix='kwc-gallery-tests-'))
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))

        self.folder_name = 'Movie (2024)'
        folder_path = self.temp_dir / self.folder_name
        folder_path.mkdir(parents=True, exist_ok=True)

        # Create a cover and sample frames
        self._write_image(folder_path / '.cover.jpg', size=(900, 1350), color=(40, 60, 120))
        self._write_image(folder_path / 'frame01.jpg', size=(1920, 1080), color=(90, 120, 180))
        self._write_image(folder_path / 'frame02.jpg', size=(2560, 1440), color=(120, 90, 150))

        # Secondary folder
        extra_folder = self.temp_dir / 'Another Title (2023)'
        extra_folder.mkdir(parents=True, exist_ok=True)
        self._write_image(extra_folder / 'still01.jpg', size=(1280, 720), color=(60, 80, 60))

        self._middleware = [
            mw for mw in settings.MIDDLEWARE
            if mw != 'whitenoise.middleware.WhiteNoiseMiddleware'
        ]

    def _write_image(self, path: Path, size: tuple[int, int] = (640, 360), color: tuple[int, int, int] = (80, 80, 80)) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new('RGB', size, color)
        img.save(path, format='JPEG', quality=90)

    def test_gallery_index_lists_media_folders(self) -> None:
        """Gallery index should list folders from WALLPAPERS_FOLDER."""
        with self.settings(WALLPAPERS_FOLDER=self.temp_dir, MIDDLEWARE=self._middleware):
            response = self.client.get(reverse('gallery:index'))

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Wallpaper library', response.content)
        self.assertIn(self.folder_name.encode(), response.content)

    def test_gallery_detail_renders_images(self) -> None:
        """Gallery detail should render images and metadata."""
        with self.settings(WALLPAPERS_FOLDER=self.temp_dir, MIDDLEWARE=self._middleware):
            response = self.client.get(reverse('gallery:detail', kwargs={'folder': self.folder_name}))

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Movie', response.content)
        self.assertIn(b'2024', response.content)

    def test_gallery_lightbox(self) -> None:
        """Gallery lightbox should display single image."""
        with self.settings(WALLPAPERS_FOLDER=self.temp_dir, MIDDLEWARE=self._middleware):
            response = self.client.get(
                reverse('gallery:lightbox', kwargs={'folder': self.folder_name, 'filename': 'frame01.jpg'})
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'frame01.jpg', response.content)
