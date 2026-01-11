"""File test cases"""

import unittest
import warnings

from file import file


class FileTestCase(unittest.TestCase):
    """File test case"""
    
    server_url = None
    namespace = None
    
    def setUp(self):
        warnings.simplefilter('ignore', ResourceWarning)
        self.namespace = ''
        self.server_url = 'https://autotest.local.vpc/api/v1'
    
    def test_file(self):
        """Test file operations"""
        self.assertEqual(True, file.main(self.server_url, self.namespace))


if __name__ == '__main__':
    unittest.main()