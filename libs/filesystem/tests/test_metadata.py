import pytest

from filesystem.metadata import FolderMetadata, MetadataError, read_metadata, write_metadata


def test_round_trip_preserves_unknown_keys(tmp_path):
    (tmp_path / ".metadata.toml").write_text('kind = "movie"\ntitle = "Film"\ncustom = "keep"\n')
    data = read_metadata(tmp_path)
    data.title = "Film 2"
    write_metadata(tmp_path, data)
    text = (tmp_path / ".metadata.toml").read_text()
    assert 'custom = "keep"' in text
    assert 'title = "Film 2"' in text


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


def test_round_trips_all_fields(tmp_path):
    data = FolderMetadata(
        kind="series",
        title="Show",
        original_title="Original",
        first_release_date="2020-01-01",
        last_release_date="2021-01-01",
        tmdb_id=9,
        copyright="(c) Studio",
        hidden=True,
    )
    write_metadata(tmp_path, data)
    assert read_metadata(tmp_path) == data


def test_write_omits_none_values(tmp_path):
    write_metadata(tmp_path, FolderMetadata(kind="other", title="Other"))
    text = (tmp_path / ".metadata.toml").read_text()
    assert "original_title" not in text
    assert "hidden" not in text
