from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.urls import reverse

import choose.api as api
from choose.models import FolderProgress, ImageDecision

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture()
def wallpapers_dir(tmp_path: Path, settings) -> Path:
	settings.WALLPAPERS_FOLDER = tmp_path
	return tmp_path


def test_decide_api_invalid_json(client) -> None:
	response = client.post(
		reverse('choose:decide', kwargs={'folder': 'Movie'}),
		data='{"filename":',
		content_type='application/json',
	)

	assert response.status_code == 400
	assert response.json() == {'error': 'invalid_json'}


def test_decide_api_missing_filename(client) -> None:
	payload = json.dumps({'decision': ImageDecision.DECISION_KEEP})
	response = client.post(
		reverse('choose:decide', kwargs={'folder': 'Movie'}),
		data=payload,
		content_type='application/json',
	)

	assert response.status_code == 400
	assert response.json() == {'error': 'missing_filename'}


def test_decide_api_invalid_decision(client) -> None:
	payload = json.dumps({'filename': 'frame01.jpg', 'decision': 'maybe'})
	response = client.post(
		reverse('choose:decide', kwargs={'folder': 'Movie'}),
		data=payload,
		content_type='application/json',
	)

	assert response.status_code == 400
	assert response.json() == {'error': 'invalid_decision'}


def test_save_api_permission_error(client, wallpapers_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	folder = wallpapers_dir / 'Clip'
	folder.mkdir()

	def deny(_path: Path) -> list[str]:
		raise PermissionError('nope')

	monkeypatch.setattr(api, 'list_image_files', deny)

	response = client.post(reverse('choose:save_api', kwargs={'folder': 'Clip'}))

	assert response.status_code == 403
	assert response.json() == {'error': 'permission_denied'}


def test_save_api_reports_delete_errors(client, wallpapers_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	folder_name = 'Show'
	folder = wallpapers_dir / folder_name
	folder.mkdir()
	(frame := folder / 'frame01.jpg').write_bytes(b'x')

	ImageDecision.objects.create(folder=folder_name, filename='frame01.jpg', decision=ImageDecision.DECISION_DELETE)

	orig_safe_remove = api.safe_remove

	def boom(path: Path) -> None:
		if path == frame:
			raise OSError('disk error')
		orig_safe_remove(path)

	monkeypatch.setattr(api, 'safe_remove', boom)

	response = client.post(reverse('choose:save_api', kwargs={'folder': folder_name}))

	assert response.status_code == 200
	payload = response.json()
	assert payload['ok'] is True
	assert payload['deleted'] == 1
	assert payload['kept'] == 0
	assert payload['delete_errors']
	assert 'disk error' in payload['delete_errors'][0]
	assert (folder / 'frame01.jpg').exists()


def test_save_api_rename_collision_fallback(client, wallpapers_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	folder_name = 'Movie (2024)'
	folder = wallpapers_dir / folder_name
	folder.mkdir()

	(folder / 'frame01.jpg').write_bytes(b'a')
	(folder / 'frame02.jpg').write_bytes(b'b')
	collision_target = folder / 'Movie 〜 0001.jpg'
	collision_target.write_bytes(b'original')

	ImageDecision.objects.create(folder=folder_name, filename='frame01.jpg', decision=ImageDecision.DECISION_KEEP)
	ImageDecision.objects.create(folder=folder_name, filename='frame02.jpg', decision=ImageDecision.DECISION_KEEP)

	orig_safe_remove = api.safe_remove

	def flaky_remove(path: Path) -> None:
		if path == collision_target:
			raise OSError('protected file')
		orig_safe_remove(path)

	monkeypatch.setattr(api, 'safe_remove', flaky_remove)

	response = client.post(reverse('choose:save_api', kwargs={'folder': folder_name}))

	assert response.status_code == 200
	payload = response.json()
	assert payload['ok'] is True
	assert payload['kept'] == 2
	files_after = {p.name for p in folder.iterdir()}
	assert 'frame01.jpg' not in files_after
	assert 'frame02.jpg' not in files_after
	assert not any(name.endswith('.renametmp') for name in files_after)
	assert any('#' in name for name in files_after)


def test_save_api_rename_failure_rolls_back(client, wallpapers_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	folder_name = 'Scene'
	folder = wallpapers_dir / folder_name
	folder.mkdir()
	(folder / 'frame01.jpg').write_bytes(b'a')

	ImageDecision.objects.create(folder=folder_name, filename='frame01.jpg', decision=ImageDecision.DECISION_KEEP)
	FolderProgress.objects.create(folder=folder_name, last_classified_name='', keep_count=0)

	orig_safe_rename = api.safe_rename

	def fail_on_final(src: Path, dest: Path) -> None:
		if '.renametmp.' in src.name and '.renametmp.' not in dest.name:
			raise OSError('rename failed')
		orig_safe_rename(src, dest)

	monkeypatch.setattr(api, 'safe_rename', fail_on_final)

	response = client.post(reverse('choose:save_api', kwargs={'folder': folder_name}))

	assert response.status_code == 500
	payload = response.json()
	assert payload['error'] == 'rename_failed'
	assert not any(p.name.endswith('.renametmp') for p in folder.iterdir())
	assert ImageDecision.objects.filter(folder=folder_name).exists()
	progress = FolderProgress.objects.get(folder=folder_name)
	assert progress.keep_count == 0


def test_save_api_transaction_rolls_back_on_error(client, wallpapers_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	folder_name = 'Clip2'
	folder = wallpapers_dir / folder_name
	folder.mkdir()
	(folder / 'frame01.jpg').write_bytes(b'a')

	ImageDecision.objects.create(folder=folder_name, filename='frame01.jpg', decision=ImageDecision.DECISION_KEEP)

	def bad_name(_name: str) -> str:
		raise ValueError('bad')

	monkeypatch.setattr(api, 'validate_folder_name', bad_name)

	response = client.post(reverse('choose:save_api', kwargs={'folder': folder_name}))

	assert response.status_code == 400
	assert response.json()['error'] == 'invalid_folder'
	assert ImageDecision.objects.filter(folder=folder_name).count() == 1
	assert not any(p.name.endswith('.renametmp') for p in folder.iterdir())


def test_save_api_episode_only_preserves_episode_number(client, wallpapers_dir: Path) -> None:
	"""Test that episode-only files (E01, E02) keep their episode numbers when renamed."""
	folder_name = 'Show'
	folder = wallpapers_dir / folder_name
	folder.mkdir()

	# Create files with episode-only format (no season)
	(folder / 'Show E01 ~ 0001.jpg').write_bytes(b'a')
	(folder / 'Show E01 ~ 0002.jpg').write_bytes(b'b')
	(folder / 'Show E02 ~ 0001.jpg').write_bytes(b'c')

	# Mark all files as keep
	ImageDecision.objects.create(folder=folder_name, filename='Show E01 ~ 0001.jpg', decision=ImageDecision.DECISION_KEEP)
	ImageDecision.objects.create(folder=folder_name, filename='Show E01 ~ 0002.jpg', decision=ImageDecision.DECISION_KEEP)
	ImageDecision.objects.create(folder=folder_name, filename='Show E02 ~ 0001.jpg', decision=ImageDecision.DECISION_KEEP)

	response = client.post(reverse('choose:save_api', kwargs={'folder': folder_name}))

	assert response.status_code == 200
	payload = response.json()
	assert payload['ok'] is True
	assert payload['kept'] == 3

	# Check the renamed files - they should preserve episode numbers
	files_after = sorted(p.name for p in folder.iterdir())
	assert len(files_after) == 3
	
	# Episode 1 files should have E01 in their names (counter resets per episode)
	# Pattern adds space before E when there's no season
	ep1_files = [f for f in files_after if 'E01' in f]
	assert len(ep1_files) == 2
	assert 'Show E01 〜 0001.jpg' in files_after
	assert 'Show E01 〜 0002.jpg' in files_after
	
	# Episode 2 file should have E02 in its name
	ep2_files = [f for f in files_after if 'E02' in f]
	assert len(ep2_files) == 1
	assert 'Show E02 〜 0001.jpg' in files_after

	# Ensure no files without episode numbers (General category)
	# This was the bug - files were being renamed to just "Show 〜 0001.jpg" without episode
	general_files = [f for f in files_after if 'E0' not in f and f.endswith('.jpg')]
	assert len(general_files) == 0, f"Files without episode numbers found: {general_files}"


def test_save_api_preserves_version_suffixes(client, wallpapers_dir: Path) -> None:
	"""Test that version suffixes (U, M, P, etc.) are preserved during rename."""
	folder_name = 'Movie (2024)'
	folder = wallpapers_dir / folder_name
	folder.mkdir()

	# Create files with version suffixes
	(folder / 'frame01.jpg').write_bytes(b'base1')
	(folder / 'frame01U.jpg').write_bytes(b'upscaled1')
	(folder / 'frame01M.jpg').write_bytes(b'mobile1')
	(folder / 'frame02.jpg').write_bytes(b'base2')
	(folder / 'frame02UM.jpg').write_bytes(b'upscaled_mobile2')

	# Mark all files as keep
	ImageDecision.objects.create(folder=folder_name, filename='frame01.jpg', decision=ImageDecision.DECISION_KEEP)
	ImageDecision.objects.create(folder=folder_name, filename='frame01U.jpg', decision=ImageDecision.DECISION_KEEP)
	ImageDecision.objects.create(folder=folder_name, filename='frame01M.jpg', decision=ImageDecision.DECISION_KEEP)
	ImageDecision.objects.create(folder=folder_name, filename='frame02.jpg', decision=ImageDecision.DECISION_KEEP)
	ImageDecision.objects.create(folder=folder_name, filename='frame02UM.jpg', decision=ImageDecision.DECISION_KEEP)

	response = client.post(reverse('choose:save_api', kwargs={'folder': folder_name}))

	assert response.status_code == 200
	payload = response.json()
	assert payload['ok'] is True
	assert payload['kept'] == 5

	files_after = {p.name for p in folder.iterdir()}
	
	# Verify base images and their versions are renamed with the same counter
	# frame01 variants should all become 0001
	assert 'Movie 〜 0001.jpg' in files_after, "Base image should be renamed to 0001"
	assert 'Movie 〜 0001U.jpg' in files_after, "U version should preserve suffix and have same counter"
	assert 'Movie 〜 0001M.jpg' in files_after, "M version should preserve suffix and have same counter"
	
	# frame02 variants should all become 0002
	assert 'Movie 〜 0002.jpg' in files_after, "Second base image should be renamed to 0002"
	assert 'Movie 〜 0002UM.jpg' in files_after, "UM version should preserve suffix and have same counter"
	
	# Verify no old filenames remain
	assert 'frame01.jpg' not in files_after
	assert 'frame01U.jpg' not in files_after
	assert 'frame02UM.jpg' not in files_after


def test_save_api_removes_invalid_suffixes(client, wallpapers_dir: Path) -> None:
	"""Test that invalid version suffixes (lowercase, repeated, too long) are removed during rename."""
	folder_name = 'Movie (2024)'
	folder = wallpapers_dir / folder_name
	folder.mkdir()

	# Create files with invalid suffixes
	(folder / 'frame01e.jpg').write_bytes(b'lowercase')  # Invalid: lowercase
	(folder / 'frame02EE.jpg').write_bytes(b'repeated')  # Invalid: repeated letter
	(folder / 'frame03EPU.jpg').write_bytes(b'toolong')  # Invalid: too long

	# Mark all files as keep
	ImageDecision.objects.create(folder=folder_name, filename='frame01e.jpg', decision=ImageDecision.DECISION_KEEP)
	ImageDecision.objects.create(folder=folder_name, filename='frame02EE.jpg', decision=ImageDecision.DECISION_KEEP)
	ImageDecision.objects.create(folder=folder_name, filename='frame03EPU.jpg', decision=ImageDecision.DECISION_KEEP)

	response = client.post(reverse('choose:save_api', kwargs={'folder': folder_name}))

	assert response.status_code == 200
	payload = response.json()
	assert payload['ok'] is True
	assert payload['kept'] == 3

	files_after = {p.name for p in folder.iterdir()}
	
	# Invalid suffixes should be removed, files renamed with proper counters
	assert 'Movie 〜 0001.jpg' in files_after
	assert 'Movie 〜 0002.jpg' in files_after
	assert 'Movie 〜 0003.jpg' in files_after
	
	# Verify no files with invalid suffixes remain
	assert not any('e.jpg' in f for f in files_after if not f.startswith('.'))
	assert not any('EE.jpg' in f for f in files_after if not f.startswith('.'))
	assert not any('EPU.jpg' in f for f in files_after if not f.startswith('.'))

