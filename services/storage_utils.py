"""Escrita atômica, backups e lock de armazenamento usando apenas a stdlib."""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import BACKUP_DIR, STORAGE_LOCK_PATH


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: str | Path, default: Any) -> Any:
    target = Path(path)
    if not target.exists():
        return default
    return json.loads(target.read_text(encoding="utf-8"))


def atomic_write_json(path: str | Path, data: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def backup_files(paths: list[str | Path], label: str) -> Path | None:
    existing = [Path(path) for path in paths if Path(path).exists()]
    if not existing:
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination = BACKUP_DIR / f"{stamp}-{label}"
    destination.mkdir(parents=True, exist_ok=False)
    for source in existing:
        shutil.copy2(source, destination / source.name)
    return destination


@contextmanager
def storage_lock(timeout_seconds: float = 30.0, stale_seconds: float = 900.0) -> Iterator[None]:
    """Lock entre processos por criação exclusiva de arquivo."""
    STORAGE_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            descriptor = os.open(STORAGE_LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(f"pid={os.getpid()} created_at={utc_now()}\n")
            break
        except FileExistsError:
            try:
                age = time.time() - STORAGE_LOCK_PATH.stat().st_mtime
                if age > stale_seconds:
                    STORAGE_LOCK_PATH.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError("Outro processo está alterando o índice; tente novamente.")
            time.sleep(0.1)
    try:
        yield
    finally:
        STORAGE_LOCK_PATH.unlink(missing_ok=True)
