from __future__ import annotations

import hashlib
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class ProviderLockError(RuntimeError):
    """Ya existe una extracción para el mismo provider y dataset."""


@contextmanager
def provider_lock(
    artifact_root: str | Path,
    *,
    provider_key: str,
    dataset_key: str,
) -> Iterator[None]:
    root = Path(artifact_root).resolve()
    lock_dir = root / ".locks"
    lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    digest = hashlib.sha256(
        f"{provider_key}\x00{dataset_key}".encode("utf-8")
    ).hexdigest()
    lock_path = lock_dir / f"{digest}.lock"
    descriptor: int | None = None
    try:
        descriptor = os.open(
            lock_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
    except FileExistsError as exc:
        raise ProviderLockError(
            "Ya existe una ejecución activa para provider_key/dataset_key."
        ) from exc
    try:
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass

