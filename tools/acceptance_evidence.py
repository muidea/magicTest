"""Create a fresh acceptance run and refuse writes into frozen evidence."""

import json
from pathlib import Path
import shutil


class EvidenceDirectory:
    def __init__(self, directory):
        self.directory = Path(directory).absolute()
        self._files = {}
        self._check_ancestors()
        self.directory.mkdir(parents=True, exist_ok=False)
        stat = self.directory.stat()
        self._identity = (stat.st_dev, stat.st_ino)

    def _check_ancestors(self):
        for ancestor in (self.directory, *self.directory.parents):
            if ancestor.is_symlink():
                raise ValueError("evidence path must not traverse a symlink")
            if (ancestor / "SHA256SUMS").exists():
                raise ValueError("frozen evidence directory refuses writes")

    def _path(self, name):
        if Path(name).name != name or name in ("", ".", "..", "SHA256SUMS"):
            raise ValueError("evidence output must be a single unfrozen filename")
        self._check_ancestors()
        stat = self.directory.stat()
        if (stat.st_dev, stat.st_ino) != self._identity:
            raise ValueError("evidence directory was replaced")
        path = self.directory / name
        if path.is_symlink():
            raise ValueError("evidence file must not be a symlink")
        return path

    def open_log(self, name):
        path = self._path(name)
        if name in self._files:
            stat = path.stat()
            if (stat.st_dev, stat.st_ino) != self._files[name]:
                raise ValueError("evidence log was replaced")
            return path.open("a")
        handle = path.open("x")
        stat = path.stat()
        self._files[name] = (stat.st_dev, stat.st_ino)
        return handle

    def copy(self, source, name=None):
        source = Path(source)
        with source.open("rb") as reader, self._path(name or source.name).open("xb") as writer:
            shutil.copyfileobj(reader, writer)

    def write_json(self, name, value):
        with self._path(name).open("x") as writer:
            json.dump(value, writer, ensure_ascii=False, indent=2)
            writer.write("\n")
