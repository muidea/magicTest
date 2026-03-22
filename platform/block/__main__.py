import os

from block import block

block.main(
    os.getenv("MAGICTEST_PLATFORM_BASE_URL", "https://autotest.local.vpc/api/v1"),
    os.getenv("MAGICTEST_PLATFORM_NAMESPACE", ""),
)
