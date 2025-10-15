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
