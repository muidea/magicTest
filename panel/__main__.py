import os
import unittest


if __name__ == "__main__":
    os.environ.setdefault("MAGICTEST_PANEL_BASE_URL", "https://autotest.local.vpc/api/v1")
    os.environ.setdefault("MAGICTEST_PANEL_NAMESPACE", "panel")
    suite = unittest.defaultTestLoader.discover(os.path.dirname(__file__), pattern="*_test.py")
    unittest.TextTestRunner(verbosity=2).run(suite)
