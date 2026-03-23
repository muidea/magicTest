import os

from access_log import access_log

access_log.main(
    os.getenv("MAGICTEST_PLATFORM_BASE_URL", "https://autotest.local.vpc/api/v1"),
    os.getenv("MAGICTEST_PLATFORM_NAMESPACE", ""),
)
