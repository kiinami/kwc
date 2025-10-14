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
	collision_target = folder / 'Movie (2024) 〜 0001.jpg'
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
