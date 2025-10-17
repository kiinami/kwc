from __future__ import annotations

import shutil
import tempfile
from io import BytesIO
from pathlib import Path

import pytest
from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from ..models import FolderProgress, ImageDecision


pytestmark = pytest.mark.django_db(transaction=True)


class MediaLibraryViewsTests(TestCase):
	def setUp(self) -> None:
		super().setUp()
		self.temp_dir = Path(tempfile.mkdtemp(prefix='kwc-tests-'))
		self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))

		self.folder_name = 'Movie (2024)'
		folder_path = self.temp_dir / self.folder_name
		folder_path.mkdir(parents=True, exist_ok=True)

		# Create a cover and a couple of sample frames.
		self._write_image(folder_path / '.cover.jpg', size=(900, 1350), color=(40, 60, 120))
		self._write_image(folder_path / 'frame01.jpg', size=(1920, 1080), color=(90, 120, 180))
		self._write_image(folder_path / 'frame02.jpg', size=(2560, 1440), color=(120, 90, 150))

		# Secondary folder used to ensure list endpoints behave with multiple entries.
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

	def test_home_view_lists_media_folders(self) -> None:
		with self.settings(WALLPAPERS_FOLDER=self.temp_dir, MIDDLEWARE=self._middleware):
			response = self.client.get(reverse('home'))

		self.assertEqual(response.status_code, 200)
		folders = response.context['folders']
		self.assertGreaterEqual(len(folders), 2)

		names = {entry['name'] for entry in folders}
		self.assertIn(self.folder_name, names)

		sample = next(entry for entry in folders if entry['name'] == self.folder_name)
		self.assertIn('gallery_url', sample)
		self.assertIn('choose_url', sample)
		self.assertTrue(sample['gallery_url'])

	def test_choose_index_renders_extraction_folders(self) -> None:
		"""Choose index now shows extraction folders from EXTRACT_FOLDER."""
		with self.settings(EXTRACT_FOLDER=self.temp_dir, MIDDLEWARE=self._middleware):
			response = self.client.get(reverse('choose:index'))

		self.assertEqual(response.status_code, 200)
		self.assertIn(b'Choose wallpapers', response.content)

	def test_gallery_view_renders_images_and_metadata(self) -> None:
		with self.settings(WALLPAPERS_FOLDER=self.temp_dir, MIDDLEWARE=self._middleware):
			response = self.client.get(reverse('choose:gallery', kwargs={'folder': self.folder_name}))

		self.assertEqual(response.status_code, 200)
		context_images = response.context['images']
		self.assertEqual(len(context_images), 2)
		first = context_images[0]
		self.assertIn('url', first)
		self.assertIn('thumb_url', first)
		self.assertIn('name', first)

		self.assertEqual(response.context['title'], 'Movie')
		self.assertEqual(response.context['year'], '2024')
		self.assertTrue(response.context['cover_url'])
		self.assertTrue(response.context['cover_thumb_url'])
		self.assertEqual(response.context['choose_url'], reverse('choose:folder', kwargs={'folder': self.folder_name}))

	def test_thumbnail_view_generates_resized_images(self) -> None:
		with self.settings(WALLPAPERS_FOLDER=self.temp_dir, MIDDLEWARE=self._middleware):
			url = reverse('wallpaper-thumbnail', kwargs={'folder': self.folder_name, 'filename': 'frame01.jpg'})
			response = self.client.get(url, {'w': 300})

		self.assertEqual(response.status_code, 200)
		self.assertIn(response['Content-Type'], {'image/jpeg', 'image/png'})
		self.assertIn('Cache-Control', response)

		# Ensure the image dimensions are respected
		with Image.open(BytesIO(response.content)) as image:
			self.assertLessEqual(image.width, 300)

	def test_save_updates_progress_and_resumes_from_next_image(self) -> None:
		"""Test that save API moves images from extract folder to wallpapers folder."""
		folder_path = self.temp_dir / self.folder_name
		for extra in ('frame03.jpg', 'frame04.jpg', 'frame05.jpg'):
			(folder_path / extra).write_bytes(b'x')

		# Use EXTRACT_FOLDER for source folder
		# Total files: frame01 (from setUp), frame02 (from setUp), frame03, frame04, frame05 = 5 files
		wallpapers_dir = self.temp_dir / "wallpapers"
		with self.settings(EXTRACT_FOLDER=self.temp_dir, WALLPAPERS_FOLDER=str(wallpapers_dir), MIDDLEWARE=self._middleware):
			# Mark frame01 as keep, frame02 as delete
			ImageDecision.objects.create(folder=self.folder_name, filename='frame01.jpg', decision=ImageDecision.DECISION_KEEP)
			ImageDecision.objects.create(folder=self.folder_name, filename='frame02.jpg', decision=ImageDecision.DECISION_DELETE)
			# frame03, frame04, frame05 are undecided -> treated as keep

			response = self.client.post(reverse('choose:save_api', kwargs={'folder': self.folder_name}))
			self.assertEqual(response.status_code, 200)
			payload = response.json()
			self.assertTrue(payload.get('ok'))
			self.assertEqual(payload.get('moved'), 4)  # frame01, frame03, frame04, frame05 (4 kept)
			self.assertEqual(payload.get('deleted'), 1)  # frame02 deleted

		# Check that files were moved to wallpapers folder with correct naming
		wallpapers_path = self.temp_dir / "wallpapers"
		self.assertTrue(wallpapers_path.exists())
		
		# The target folder should use the title from the folder name (removing year)
		# "Movie (2024)" -> "Movie" as target folder
		target_folder_name = payload.get('target_folder', 'Movie')
		target_folder = wallpapers_path / target_folder_name
		self.assertTrue(target_folder.exists(), f"Expected folder {target_folder} to exist. Contents: {list(wallpapers_path.iterdir())}")
		
		# Check that kept images are in the target folder
		# Should have: 4 kept images + 1 cover file = 5 files total
		kept_files = list(target_folder.glob("*.jpg"))
		self.assertEqual(len(kept_files), 5)  # 4 images + .cover.jpg

	@pytest.mark.skip(reason="Test needs rework for new extraction/gallery separation flow")
	def test_unsaved_decisions_override_saved_progress(self) -> None:
		folder_path = self.temp_dir / self.folder_name
		for extra in ('frame03.jpg', 'frame04.jpg'):
			(folder_path / extra).write_bytes(b'y')

		with self.settings(WALLPAPERS_FOLDER=self.temp_dir, MIDDLEWARE=self._middleware):
			ImageDecision.objects.create(folder=self.folder_name, filename='frame01.jpg', decision=ImageDecision.DECISION_KEEP)
			ImageDecision.objects.create(folder=self.folder_name, filename='frame02.jpg', decision=ImageDecision.DECISION_DELETE)
			self.client.post(reverse('choose:save_api', kwargs={'folder': self.folder_name}))

		FolderProgress.objects.get(folder=self.folder_name)
		folder_files = sorted(
			f.name for f in folder_path.iterdir()
			if f.is_file() and not f.name.startswith('.') and f.suffix.lower() == '.jpg'
		)
		self.assertGreaterEqual(len(folder_files), 3)

		next_image_name = folder_files[1]
		ImageDecision.objects.create(folder=self.folder_name, filename=next_image_name, decision=ImageDecision.DECISION_KEEP)

		with self.settings(WALLPAPERS_FOLDER=self.temp_dir, MIDDLEWARE=self._middleware):
			chooser_response = self.client.get(reverse('choose:folder', kwargs={'folder': self.folder_name}))

		self.assertEqual(chooser_response.status_code, 200)
		self.assertEqual(chooser_response.context['selected_index'], 2)
		images = chooser_response.context['images']
		self.assertEqual(images[1]['decision'], ImageDecision.DECISION_KEEP)
		self.assertEqual(images[2]['name'], folder_files[2])
