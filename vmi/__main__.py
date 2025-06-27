import unittest
from base_test_case import BaseTestCase

if __name__ == '__main__':
    test_loader = unittest.TestLoader()
    test_suite = test_loader.loadTestsFromTestCase(BaseTestCase)
    test_runner = unittest.TextTestRunner()
    result = test_runner.run(test_suite)
