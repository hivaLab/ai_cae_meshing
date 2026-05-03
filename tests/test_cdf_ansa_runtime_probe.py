from __future__ import annotations

import json
from pathlib import Path

import cad_dataset_factory.cdf.oracle.ansa_probe as ansa_probe
from cad_dataset_factory.cdf.cli import main as cdf_main
from cad_dataset_factory.cdf.oracle import run_ansa_probe

ROOT = Path(__file__).resolve().parents[1]


def _fake_executable() -> Path:
    path = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_ansa_runtime_probe" / "bin" / "ansa64.bat"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("@echo off\n", encoding="utf-8")
    return path


def test_probe_missing_executable_writes_structured_report() -> None:
    out = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_ansa_runtime_probe" / "missing" / "probe.json"

    result = run_ansa_probe(ansa_executable=out.parent / "does_not_exist.bat", out=out)

    assert result.status == "FAILED"
    assert result.error_code == "ansa_executable_not_found"
    assert out.is_file()
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["schema"] == "CDF_ANSA_RUNTIME_PROBE_SM_V1"


def test_probe_launches_ansa_script_command_and_reads_report(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    executable = _fake_executable()
    out = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_ansa_runtime_probe" / "ok" / "probe.json"
    captured: dict[str, object] = {}

    class Completed:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(command, capture_output, text, timeout, check):  # type: ignore[no-untyped-def]
        captured["command"] = command
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text('{"schema":"CDF_ANSA_RUNTIME_PROBE_SM_V1","status":"OK"}\n', encoding="utf-8")
        return Completed()

    monkeypatch.setattr(ansa_probe.subprocess, "run", fake_run)

    result = run_ansa_probe(ansa_executable=executable, out=out, timeout_sec=7)

    assert result.status == "OK"
    assert result.returncode == 0
    command = captured["command"]
    assert isinstance(command, list)
    assert command[0] == executable.resolve().as_posix()
    assert any(str(item).startswith("load_script:") for item in command)
    assert any(str(item).startswith("-process_string:") for item in command)


def test_cli_ansa_probe_returns_blocked_for_missing_executable() -> None:
    out = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_ansa_runtime_probe" / "cli" / "probe.json"

    exit_code = cdf_main(["ansa-probe", "--ansa-executable", (out.parent / "missing.bat").as_posix(), "--out", out.as_posix()])

    assert exit_code == 2
    assert out.is_file()
