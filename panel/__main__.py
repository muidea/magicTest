import os
import unittest


if __name__ == "__main__":
    os.environ.setdefault("MAGICTEST_PANEL_BASE_URL", "https://autotest.local.vpc/api/v1")
    os.environ.setdefault("MAGICTEST_PANEL_NAMESPACE", "panel")
    unittest.main(module="application_lifecycle_test", verbosity=2)
