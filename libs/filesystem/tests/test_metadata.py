import pytest

from filesystem.metadata import FolderMetadata, MetadataError, read_metadata, write_metadata


def test_missing_returns_none(tmp_path):
    assert read_metadata(tmp_path) is None


def test_malformed_raises(tmp_path):
    (tmp_path / ".metadata.toml").write_text("not = [valid")
    with pytest.raises(MetadataError):
        read_metadata(tmp_path)


def test_invalid_utf8_raises_metadata_error(tmp_path):
    (tmp_path / ".metadata.toml").write_bytes(b'title = "\xff"')
    with pytest.raises(MetadataError):
        read_metadata(tmp_path)


def test_round_trips_movie_data(tmp_path):
    data = FolderMetadata(
        original_title="Original",
        release_date="2001-01-01",
        copyright="(c) Studio",
    )
    write_metadata(tmp_path, data)
    assert read_metadata(tmp_path) == data


def test_round_trips_series_and_season_dates(tmp_path):
    data = FolderMetadata(
        original_title="Original Show",
        first_release_date="2020-01-01",
        last_release_date="2021-01-01",
    )
    write_metadata(tmp_path, data)
    assert read_metadata(tmp_path) == data


def test_round_trip_preserves_unknown_keys(tmp_path):
    (tmp_path / ".metadata.toml").write_text('original_title = "Original"\ncustom = "keep"\n')
    data = read_metadata(tmp_path)
    data.original_title = "Changed"
    write_metadata(tmp_path, data)
    text = (tmp_path / ".metadata.toml").read_text()
    assert 'custom = "keep"' in text
    assert 'original_title = "Changed"' in text


def test_write_omits_empty_values(tmp_path):
    write_metadata(tmp_path, FolderMetadata(hidden=False))
    text = (tmp_path / ".metadata.toml").read_text()
    assert "original_title" not in text
    assert "release_date" not in text
    assert "hidden" not in text


def test_hidden_round_trips(tmp_path):
    write_metadata(tmp_path, FolderMetadata(hidden=True))
    assert read_metadata(tmp_path).hidden is True
