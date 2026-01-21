import unittest
import warnings

from account import account
from endpoint import endpoint
from namespace import namespace
from role import role


class MyTestCase(unittest.TestCase):
    server_url = None
    namespace = None

    def setUp(self):
        warnings.simplefilter('ignore', ResourceWarning)
        self.namespace = ''
        self.server_url = 'https://autotest.remote.vpc'

    def test_account(self):
        self.assertEqual(True, account.main(self.server_url, self.namespace))

    def test_endpoint(self):
        self.assertEqual(True, endpoint.main(self.server_url, self.namespace))

    def test_role(self):
        self.assertEqual(True, role.main(self.server_url, self.namespace))

    def test_namespace(self):
        self.assertEqual(True, namespace.main(self.server_url, self.namespace))


if __name__ == '__main__':
    unittest.main()
