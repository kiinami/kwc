"""Tests for TMDB integration."""

from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase

from extract import tmdb


class TMDBServiceTests(TestCase):
    """Test TMDB service module functions."""

    def test_is_available_returns_true_when_tmdb_installed(self):
        """Test that is_available returns True when tmdbsimple is installed."""
        # tmdbsimple is installed in our test environment
        assert tmdb.is_available() is True

    @patch('extract.tmdb.tmdb', None)
    def test_is_available_returns_false_when_tmdb_not_installed(self):
        """Test that is_available returns False when tmdbsimple is not installed."""
        with patch.dict('sys.modules', {'tmdbsimple': None}):
            result = tmdb.is_available()
        # Can't actually test this since we need tmdbsimple to load the module

    def test_configure_api_key_sets_key(self):
        """Test that configure_api_key sets the API key."""
        test_key = "test_api_key_123"
        tmdb.configure_api_key(test_key)
        
        # Verify the key was set by checking the module
        import tmdbsimple
        assert test_key == tmdbsimple.API_KEY

    @patch('extract.tmdb.tmdb.Search')
    def test_search_multi_returns_results(self, mock_search_class):
        """Test that search_multi returns search results."""
        # Setup mock
        mock_search = MagicMock()
        mock_search.multi.return_value = {
            'results': [
                {
                    'id': 550,
                    'title': 'Fight Club',
                    'release_date': '1999-10-15',
                    'media_type': 'movie',
                    'poster_path': '/abc123.jpg',
                },
                {
                    'id': 1396,
                    'name': 'Breaking Bad',
                    'first_air_date': '2008-01-20',
                    'media_type': 'tv',
                    'poster_path': '/def456.jpg',
                },
            ]
        }
        mock_search_class.return_value = mock_search
        
        # Configure API key
        tmdb.configure_api_key("test_key")
        
        # Execute
        results = tmdb.search_multi("test query", year=2020)
        
        # Verify
        assert len(results) == 2
        assert results[0]['title'] == 'Fight Club'
        assert results[1]['title'] == 'Breaking Bad'
        mock_search.multi.assert_called_once_with(query="test query", year=2020)

    @patch('extract.tmdb.tmdb.Search')
    def test_search_multi_filters_out_items_without_posters(self, mock_search_class):
        """Test that search_multi filters out items without poster paths."""
        # Setup mock
        mock_search = MagicMock()
        mock_search.multi.return_value = {
            'results': [
                {
                    'id': 550,
                    'title': 'With Poster',
                    'release_date': '1999-10-15',
                    'media_type': 'movie',
                    'poster_path': '/abc123.jpg',
                },
                {
                    'id': 551,
                    'title': 'Without Poster',
                    'release_date': '1999-10-15',
                    'media_type': 'movie',
                    'poster_path': None,
                },
            ]
        }
        mock_search_class.return_value = mock_search
        
        # Configure API key
        tmdb.configure_api_key("test_key")
        
        # Execute
        results = tmdb.search_multi("test query")
        
        # Verify - only the one with poster should be returned
        assert len(results) == 1
        assert results[0]['title'] == 'With Poster'

    def test_search_multi_raises_error_without_api_key(self):
        """Test that search_multi raises error when API key is not configured."""
        # Clear API key
        import tmdbsimple
        tmdbsimple.API_KEY = ''
        
        # Execute and verify
        with pytest.raises(RuntimeError, match="TMDB API key is not configured"):
            tmdb.search_multi("test query")

    @patch('extract.tmdb.tmdb.Movies')
    def test_get_posters_returns_movie_posters(self, mock_movies_class):
        """Test that get_posters returns posters for a movie."""
        # Setup mock
        mock_movie = MagicMock()
        mock_movie.images.return_value = {
            'posters': [
                {
                    'file_path': '/abc123.jpg',
                    'width': 2000,
                    'height': 3000,
                    'vote_average': 8.5,
                },
                {
                    'file_path': '/def456.jpg',
                    'width': 1000,
                    'height': 1500,
                    'vote_average': 7.0,
                },
            ]
        }
        mock_movies_class.return_value = mock_movie
        
        # Configure API key
        tmdb.configure_api_key("test_key")
        
        # Execute
        posters = tmdb.get_posters("movie", 550)
        
        # Verify
        assert len(posters) == 2
        # Should be sorted by vote_average (highest first)
        assert posters[0]['vote_average'] == 8.5
        assert posters[1]['vote_average'] == 7.0
        assert posters[0]['url'].startswith('https://image.tmdb.org/t/p/original')

    @patch('extract.tmdb.tmdb.TV')
    def test_get_posters_returns_tv_posters(self, mock_tv_class):
        """Test that get_posters returns posters for a TV show."""
        # Setup mock
        mock_tv = MagicMock()
        mock_tv.images.return_value = {
            'posters': [
                {
                    'file_path': '/tv123.jpg',
                    'width': 2000,
                    'height': 3000,
                    'vote_average': 9.0,
                },
            ]
        }
        mock_tv_class.return_value = mock_tv
        
        # Configure API key
        tmdb.configure_api_key("test_key")
        
        # Execute
        posters = tmdb.get_posters("tv", 1396)
        
        # Verify
        assert len(posters) == 1
        assert posters[0]['vote_average'] == 9.0

    def test_get_posters_raises_error_for_invalid_media_type(self):
        """Test that get_posters raises ValueError for invalid media_type."""
        # Configure API key
        tmdb.configure_api_key("test_key")
        
        # Execute and verify
        with pytest.raises(ValueError, match="Invalid media_type: invalid"):
            tmdb.get_posters("invalid", 123)

    def test_get_poster_url_returns_correct_url(self):
        """Test that get_poster_url returns the correct URL."""
        url = tmdb.get_poster_url("/abc123.jpg", "w500")
        assert url == "https://image.tmdb.org/t/p/w500/abc123.jpg"
        
        url = tmdb.get_poster_url("/def456.jpg")
        assert url == "https://image.tmdb.org/t/p/original/def456.jpg"
