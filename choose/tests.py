from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse


class MediaLibraryViewsTests(TestCase):
	def setUp(self) -> None:
		super().setUp()
		self.temp_dir = Path(tempfile.mkdtemp(prefix='kwc-tests-'))
		self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))

		self.folder_name = 'Movie (2024)'
		folder_path = self.temp_dir / self.folder_name
		folder_path.mkdir(parents=True, exist_ok=True)

		# Create a cover and a couple of fake frames.
		(folder_path / '.cover.jpg').write_bytes(b'cover')
		(folder_path / 'frame01.jpg').write_bytes(b'a')
		(folder_path / 'frame02.jpg').write_bytes(b'b')

		# Secondary folder used to ensure list endpoints behave with multiple entries.
		extra_folder = self.temp_dir / 'Another Title (2023)'
		extra_folder.mkdir(parents=True, exist_ok=True)
		(extra_folder / 'still01.jpg').write_bytes(b'c')

		self._middleware = [
			mw for mw in settings.MIDDLEWARE
			if mw != 'whitenoise.middleware.WhiteNoiseMiddleware'
		]

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

	def test_gallery_view_renders_images_and_metadata(self) -> None:
		with self.settings(WALLPAPERS_FOLDER=self.temp_dir, MIDDLEWARE=self._middleware):
			response = self.client.get(reverse('choose:gallery', kwargs={'folder': self.folder_name}))

		self.assertEqual(response.status_code, 200)
		context_images = response.context['images']
		self.assertEqual(len(context_images), 2)
		first = context_images[0]
		self.assertIn('url', first)
		self.assertIn('name', first)

		self.assertEqual(response.context['title'], 'Movie')
		self.assertEqual(response.context['year'], '2024')
		self.assertTrue(response.context['cover_url'])
		self.assertEqual(response.context['choose_url'], reverse('choose:folder', kwargs={'folder': self.folder_name}))

