"""Adapter boundary (effdir-editor-spec.md, "Adapter boundary"): decouples
layer-3 editor code from where EFFDIR bytes physically live (inside a DBPF
archive vs. a raw extracted file on disk).
"""

from __future__ import annotations

import abc
import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Optional

from .dbpf import DbpfArchive, Tgi, replace_entry_and_save

DEFAULT_EFFDIR_TGI = "EA5118B0-EA5118B1-00000001"


@dataclass(frozen=True)
class ResourceHandle:
    package_path: str
    tgi: str


@dataclass(frozen=True)
class WriteOptions:
    output_path: Optional[str] = None


@dataclass(frozen=True)
class WriteResult:
    path: str


class EffDirSource(abc.ABC):
    @abc.abstractmethod
    def inspect(self, handle: ResourceHandle):
        ...

    @abc.abstractmethod
    def read(self, handle: ResourceHandle) -> bytes:
        ...

    @abc.abstractmethod
    def write(self, handle: ResourceHandle, data: bytes, write_options: WriteOptions) -> WriteResult:
        ...

    @abc.abstractmethod
    def backup(self, handle: ResourceHandle) -> str:
        ...


class DbpfEffDirSource(EffDirSource):
    def inspect(self, handle: ResourceHandle):
        archive = DbpfArchive.open(handle.package_path)
        tgi = Tgi.parse(handle.tgi or DEFAULT_EFFDIR_TGI)
        return archive.find(tgi)

    def read(self, handle: ResourceHandle) -> bytes:
        archive = DbpfArchive.open(handle.package_path)
        tgi = Tgi.parse(handle.tgi or DEFAULT_EFFDIR_TGI)
        return archive.read_decompressed(tgi)

    def write(self, handle: ResourceHandle, data: bytes, write_options: WriteOptions) -> WriteResult:
        tgi = Tgi.parse(handle.tgi or DEFAULT_EFFDIR_TGI)
        output_path = write_options.output_path or handle.package_path
        replace_entry_and_save(handle.package_path, output_path, tgi, data)
        return WriteResult(path=output_path)

    def backup(self, handle: ResourceHandle) -> Optional[str]:
        if not os.path.exists(handle.package_path):
            return None  # nothing on disk yet (first save of a new resource)
        backup_path = handle.package_path + ".bak"
        if not os.path.exists(backup_path):
            shutil.copy2(handle.package_path, backup_path)
        return backup_path


class LocalFileEffDirSource(EffDirSource):
    """Treats package_path as a raw, already-decompressed EFFDIR blob with
    no DBPF wrapper. handle.tgi is ignored."""

    def inspect(self, handle: ResourceHandle):
        return os.stat(handle.package_path)

    def read(self, handle: ResourceHandle) -> bytes:
        with open(handle.package_path, "rb") as f:
            return f.read()

    def write(self, handle: ResourceHandle, data: bytes, write_options: WriteOptions) -> WriteResult:
        output_path = write_options.output_path or handle.package_path
        directory = os.path.dirname(os.path.abspath(output_path)) or "."
        fd, tmp_path = tempfile.mkstemp(dir=directory)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp_path, output_path)
        except BaseException:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
        return WriteResult(path=output_path)

    def backup(self, handle: ResourceHandle) -> Optional[str]:
        if not os.path.exists(handle.package_path):
            return None  # nothing on disk yet (first save of a new resource)
        backup_path = handle.package_path + ".bak"
        if not os.path.exists(backup_path):
            shutil.copy2(handle.package_path, backup_path)
        return backup_path
