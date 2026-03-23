import os

from totalizator import totalizator

totalizator.main(
    os.getenv("MAGICTEST_PLATFORM_BASE_URL", "https://autotest.local.vpc/api/v1"),
    os.getenv("MAGICTEST_PLATFORM_NAMESPACE", ""),
)
