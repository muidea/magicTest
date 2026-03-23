import os

from operation_log import operation_log

operation_log.main(
    os.getenv("MAGICTEST_PLATFORM_BASE_URL", "https://autotest.local.vpc/api/v1"),
    os.getenv("MAGICTEST_PLATFORM_NAMESPACE", ""),
)
