"""Compatibility entrypoint for the current file smoke flow."""

from file import file


def main(server_url, namespace):
    return file.main(server_url, namespace)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("用法: python file.py <server_url> <namespace>")
        sys.exit(1)

    server_url = sys.argv[1]
    namespace = sys.argv[2]

    success = main(server_url, namespace)
    sys.exit(0 if success else 1)
