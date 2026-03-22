import os

from file import file

file.main(
    os.getenv('MAGICTEST_FILE_BASE_URL', 'https://autotest.local.vpc'),
    os.getenv('MAGICTEST_FILE_NAMESPACE', ''),
)
