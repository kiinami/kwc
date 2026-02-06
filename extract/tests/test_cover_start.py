import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from extract.job_runner import JobRunner
from extract.models import ExtractionJob


class StartCoverCopyTest(TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.wallpapers_dir = Path(self.tmp_dir) / "wallpapers"
        self.extract_dir = Path(self.tmp_dir) / "extract"
        self.wallpapers_dir.mkdir()
        self.extract_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    @patch("choose.utils.find_cover_filename")
    @patch("extract.views.job_runner.start_job")
    def test_start_view_detects_cover(self, mock_start_job, mock_find_cover):
        # Setup existing library folder with cover
        folder_name = "Test Movie (2020)"
        lib_folder = self.wallpapers_dir / folder_name
        lib_folder.mkdir()
        cover_file = lib_folder / ".cover.jpg"
        cover_file.touch()

        # Mock settings to point to our temp dirs
        with override_settings(WALLPAPERS_FOLDER=str(self.wallpapers_dir), EXTRACTION_FOLDER=str(self.extract_dir)):
            mock_find_cover.return_value = ".cover.jpg"

            client = Client()
            # Form data matches the folder
            data = {
                "video": "/tmp/video.mp4",
                "title": "Test Movie",
                "year": "2020",
            }

            # Mock form validation checks for video file
            with (
                patch("extract.forms.os.path.exists", return_value=True),
                patch("extract.forms.os.path.isfile", return_value=True),
                patch("extract.forms.os.path.isabs", return_value=True),
            ):
                response = client.post(reverse("extract:start"), data)

            self.assertEqual(response.status_code, 302)

            # Check created job
            job = ExtractionJob.objects.last()
            self.assertIsNotNone(job)
            self.assertIn("source_cover_path", job.params)
            self.assertEqual(job.params["source_cover_path"], str(cover_file))


class JobRunnerCoverCopyTest(TestCase):
    def test_copy_cover_image(self):
        runner = JobRunner()

        with patch("shutil.copy2") as mock_copy:
            source = Path("/tmp/source/.cover.jpg")
            output = Path("/tmp/output")

            # We need source.exists() to return true
            with patch.object(Path, "exists") as mock_exists, patch.object(Path, "mkdir"):
                mock_exists.return_value = True
                runner._copy_cover_image(source, output)

                mock_copy.assert_called_once()
                args, _ = mock_copy.call_args
                self.assertEqual(args[0], source)
                self.assertEqual(args[1], output / ".cover.jpg")
