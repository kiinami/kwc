
from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from pathlib import Path

class FoldersApiTest(TestCase):
    def test_folders_api_merges_library_and_inbox(self):
        """Test that folders_api merges folders from both library and inbox."""
        
        # Mock list_media_folders to return different sets of folders
        with patch('choose.utils.list_media_folders') as mock_list:
            # Define side_effect to return different lists based on arguments
            # First call has no args (Library), second has root (Inbox)
            
            library_folders = [
                {'name': 'UniqueLib (2020)', 'title': 'UniqueLib', 'year_raw': 2020, 'year_sort': 2020, 'mtime': 100, 'cover_url': 'lib_url', 'cover_thumb_url': 'lib_thumb'},
                {'name': 'Shared (2021)', 'title': 'Shared', 'year_raw': 2021, 'year_sort': 2021, 'mtime': 200, 'cover_url': 'shared_lib_url', 'cover_thumb_url': 'shared_lib_thumb'},
            ]
            
            inbox_folders = [
                {'name': 'Shared (2021)', 'title': 'Shared', 'year_raw': 2021, 'year_sort': 2021, 'mtime': 300, 'cover_url': 'shared_inbox_url', 'cover_thumb_url': 'shared_inbox_thumb'},
                {'name': 'UniqueInbox (2022)', 'title': 'UniqueInbox', 'year_raw': 2022, 'year_sort': 2022, 'mtime': 400, 'cover_url': 'inbox_url', 'cover_thumb_url': 'inbox_thumb'},
            ]

            def side_effect(root=None):
                if root is None:
                    return library_folders, Path('/lib')
                return inbox_folders, Path('/inbox')

            mock_list.side_effect = side_effect

            client = Client()
            response = client.get(reverse('extract:folders_api'))
            
            self.assertEqual(response.status_code, 200)
            data = response.json()
            folders = data['folders']
            
            # Verify result count (should be 3: UniqueLib, Shared, UniqueInbox)
            self.assertEqual(len(folders), 3)
            
            names = [f['name'] for f in folders]
            self.assertIn('UniqueLib (2020)', names)
            self.assertIn('Shared (2021)', names)
            self.assertIn('UniqueInbox (2022)', names)
            
            # Verify Shared came from Library (inserted first in the loop in views.py)
            shared = next(f for f in folders if f['name'] == 'Shared (2021)')
            self.assertEqual(shared['cover_url'], 'shared_lib_url')
