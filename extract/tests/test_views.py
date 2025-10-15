import pytest
from django.test import Client
from django.urls import reverse

from extract.models import ExtractionJob


@pytest.mark.django_db
def test_job_view_includes_gallery_url():
	"""Test that the job view includes a gallery_url in the context."""
	# Create a test extraction job with an output directory
	job = ExtractionJob.objects.create(
		id="test-job-123",
		params={"title": "Test Movie"},
		output_dir="/test/path/Test Movie (2024)",
		status=ExtractionJob.Status.DONE,
	)
	
	client = Client()
	response = client.get(reverse('extract:job', kwargs={'job_id': job.id}))
	
	assert response.status_code == 200
	assert 'gallery_url' in response.context
	# The gallery_url should be for the folder "Test Movie (2024)"
	expected_url = reverse('choose:gallery', kwargs={'folder': 'Test Movie (2024)'})
	assert response.context['gallery_url'] == expected_url


@pytest.mark.django_db
def test_job_view_button_text_is_open_gallery():
	"""Test that the job view button says 'Open Gallery' instead of 'Open Choose'."""
	job = ExtractionJob.objects.create(
		id="test-job-456",
		params={"title": "Another Movie"},
		output_dir="/test/path/Another Movie",
		status=ExtractionJob.Status.DONE,
	)
	
	client = Client()
	response = client.get(reverse('extract:job', kwargs={'job_id': job.id}))
	
	assert response.status_code == 200
	content = response.content.decode('utf-8')
	assert 'Open Gallery' in content
	assert 'Open Choose' not in content


@pytest.mark.django_db
def test_browse_api_returns_no_store_cache_header():
	"""Test that the browse_api endpoint returns Cache-Control: no-store header."""
	client = Client()
	
	# Test with root path
	response = client.get(reverse('extract:browse_api'), {'path': '/', 'dirs_only': '1'})
	assert 'Cache-Control' in response
	assert response['Cache-Control'] == 'no-store'
	
	# Test with not found path
	response = client.get(reverse('extract:browse_api'), {'path': '/nonexistent/path/xyz'})
	assert response.status_code == 404
	assert 'Cache-Control' in response
	assert response['Cache-Control'] == 'no-store'


@pytest.mark.django_db
def test_job_view_displays_filename():
	"""Test that the job view displays the filename from the name field."""
	job = ExtractionJob.objects.create(
		id="test-job-789",
		name="my_video.mp4",
		params={"title": "Test Movie"},
		output_dir="/test/path/Test Movie",
		status=ExtractionJob.Status.DONE,
	)
	
	client = Client()
	response = client.get(reverse('extract:job', kwargs={'job_id': job.id}))
	
	assert response.status_code == 200
	content = response.content.decode('utf-8')
	assert 'my_video.mp4' in content


@pytest.mark.django_db
def test_job_view_falls_back_to_extraction_when_no_name():
	"""Test that the job view displays 'Extraction' when name is empty."""
	job = ExtractionJob.objects.create(
		id="test-job-101",
		name="",
		params={"title": "Test Movie"},
		output_dir="/test/path/Test Movie",
		status=ExtractionJob.Status.DONE,
	)
	
	client = Client()
	response = client.get(reverse('extract:job', kwargs={'job_id': job.id}))
	
	assert response.status_code == 200
	content = response.content.decode('utf-8')
	assert 'Extraction' in content


@pytest.mark.django_db
def test_job_api_includes_name():
	"""Test that the job API endpoint returns the job name."""
	job = ExtractionJob.objects.create(
		id="test-job-202",
		name="video_file.mkv",
		params={"title": "Test Show"},
		output_dir="/test/path/Test Show",
		status=ExtractionJob.Status.RUNNING,
	)
	
	client = Client()
	response = client.get(reverse('extract:job_api', kwargs={'job_id': job.id}))
	
	assert response.status_code == 200
	data = response.json()
	assert data['name'] == "video_file.mkv"


@pytest.mark.django_db
def test_jobs_api_includes_names():
	"""Test that the jobs API endpoint returns job names."""
	ExtractionJob.objects.create(
		id="test-job-303",
		name="first_video.mp4",
		params={"title": "First"},
		output_dir="/test/path/First",
		status=ExtractionJob.Status.DONE,
	)
	ExtractionJob.objects.create(
		id="test-job-404",
		name="second_video.mp4",
		params={"title": "Second"},
		output_dir="/test/path/Second",
		status=ExtractionJob.Status.RUNNING,
	)
	
	client = Client()
	response = client.get(reverse('extract:jobs_api'))
	
	assert response.status_code == 200
	data = response.json()
	jobs = data['jobs']
	assert len(jobs) == 2
	job_names = [j['name'] for j in jobs]
	assert "first_video.mp4" in job_names
	assert "second_video.mp4" in job_names


@pytest.mark.django_db
def test_start_view_extracts_filename_from_video_path(tmp_path):
	"""Test that creating a job via the start view extracts the filename."""
	# Create a dummy video file
	video_file = tmp_path / "my_test_video.mkv"
	video_file.write_text("fake video")
	
	client = Client()
	response = client.post(reverse('extract:start'), {
		'video': str(video_file),
		'title': 'Test Movie',
		'trim_intervals': '[]',
	})
	
	# Should redirect to job page
	assert response.status_code == 302
	
	# Extract job ID from redirect URL
	job_url = response.url
	job_id = job_url.split('/')[-2]
	
	# Verify the job was created with the correct name
	job = ExtractionJob.objects.get(id=job_id)
	assert job.name == "my_test_video.mkv"


@pytest.mark.django_db
def test_folders_api_returns_existing_folders(tmp_path, settings):
	"""Test that the folders API returns existing wallpaper folders."""
	# Set up temporary wallpapers folder
	settings.WALLPAPERS_FOLDER = str(tmp_path)
	
	# Create some test folders
	(tmp_path / "Movie A (2020)").mkdir()
	(tmp_path / "Movie A (2020)" / "test.jpg").write_text("fake image")
	(tmp_path / "Show B (2021)").mkdir()
	(tmp_path / "Show B (2021)" / "test.jpg").write_text("fake image")
	(tmp_path / "Movie C").mkdir()
	(tmp_path / "Movie C" / "test.jpg").write_text("fake image")
	
	client = Client()
	response = client.get(reverse('extract:folders_api'))
	
	assert response.status_code == 200
	data = response.json()
	assert 'folders' in data
	
	folders = data['folders']
	assert len(folders) == 3
	
	# Check that folders contain the expected structure
	folder_names = {f['name'] for f in folders}
	assert "Movie A (2020)" in folder_names
	assert "Show B (2021)" in folder_names
	assert "Movie C" in folder_names
	
	# Check that title and year are parsed correctly
	movie_a = next(f for f in folders if f['name'] == "Movie A (2020)")
	assert movie_a['title'] == "Movie A"
	assert movie_a['year'] == 2020
	
	movie_c = next(f for f in folders if f['name'] == "Movie C")
	assert movie_c['title'] == "Movie C"
	assert movie_c['year'] is None


@pytest.mark.django_db
def test_browse_api_uses_default_start_path(tmp_path, settings):
	"""Test that the browse API uses FILE_PICKER_START_PATH as default when no path is provided."""
	# Create a test directory structure
	test_dir = tmp_path / "custom" / "start"
	test_dir.mkdir(parents=True)
	(test_dir / "test_file.mp4").write_text("fake video")
	
	# Set the FILE_PICKER_START_PATH to our custom directory
	settings.FILE_PICKER_START_PATH = str(test_dir)
	
	client = Client()
	# Call browse_api without providing a path parameter
	response = client.get(reverse('extract:browse_api'))
	
	assert response.status_code == 200
	data = response.json()
	assert data['path'] == str(test_dir)
	assert len(data['entries']) == 1
	assert data['entries'][0]['name'] == 'test_file.mp4'


@pytest.mark.django_db
def test_start_view_includes_file_picker_start_path(settings):
	"""Test that the start view includes file_picker_start_path in context."""
	settings.FILE_PICKER_START_PATH = '/custom/path'
	
	client = Client()
	response = client.get(reverse('extract:start'))
	
	assert response.status_code == 200
	assert 'file_picker_start_path' in response.context
	assert response.context['file_picker_start_path'] == '/custom/path'
