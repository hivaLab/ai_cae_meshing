from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path


def extract_job_package(job: Path | str, workdir: Path | str | None = None) -> Path:
    job = Path(job)
    if job.is_dir():
        return job
    if workdir is None:
        workdir = Path(tempfile.mkdtemp(prefix="amg_job_"))
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(job, "r") as archive:
        archive.extractall(workdir)
    return workdir
