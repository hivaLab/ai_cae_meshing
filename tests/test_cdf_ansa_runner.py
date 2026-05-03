from __future__ import annotations

from pathlib import Path
import base64
import json

import pytest

import cad_dataset_factory.cdf.oracle.ansa_runner as ansa_runner
from cad_dataset_factory.cdf.config import load_cdf_config
from cad_dataset_factory.cdf.oracle import (
    AnsaRunRequest,
    AnsaRunnerConfig,
    AnsaRunnerError,
    build_ansa_batch_command,
    preflight_ansa_run,
    resolve_ansa_executable,
    run_ansa_oracle,
)

ROOT = Path(__file__).resolve().parents[1]


def _decode_process_payload(command: list[str]) -> dict:
    payload_arg = next(item for item in command if item.startswith("-process_string:"))
    encoded = payload_arg[len("-process_string:") :]
    padded = encoded + "=" * (-len(encoded) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))


def _sample_dir(name: str = "sample_000401", *, with_manifest: bool = True) -> Path:
    root = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_ansa_runner" / "samples" / name
    (root / "labels").mkdir(parents=True, exist_ok=True)
    manifest = root / "labels" / "amg_manifest.json"
    if with_manifest:
        manifest.write_text('{"schema_version":"AMG_MANIFEST_SM_V1"}\n', encoding="utf-8")
    elif manifest.exists():
        manifest.unlink()
    return root


def _fake_executable(name: str = "ansa64.exe") -> Path:
    path = ROOT / "runs" / "pytest_tmp_local" / "test_cdf_ansa_runner" / "bin" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fake ansa executable\n", encoding="utf-8")
    return path


def _request(*, env: dict[str, str] | None = None, timeout: int = 180, with_manifest: bool = True) -> AnsaRunRequest:
    config = AnsaRunnerConfig(
        ansa_executable="${ANSA_EXECUTABLE}",
        timeout_sec_per_sample=timeout,
    )
    return AnsaRunRequest(sample_dir=_sample_dir(with_manifest=with_manifest), config=config, repo_root=ROOT, env=env)


def test_default_cdf_ansa_oracle_config_normalizes() -> None:
    config = AnsaRunnerConfig.model_validate(load_cdf_config()["ansa_oracle"])

    assert config.enabled is True
    assert config.ansa_executable == "${ANSA_EXECUTABLE}"
    assert config.batch_mesh_session == "AMG_SHELL_CONST_THICKNESS_V1"
    assert config.timeout_sec_per_sample == 180


def test_resolve_ansa_executable_uses_env_deterministically() -> None:
    executable = _fake_executable()

    resolved = resolve_ansa_executable("${ANSA_EXECUTABLE}", {"ANSA_EXECUTABLE": executable.as_posix()})

    assert resolved == executable


def test_missing_ansa_executable_returns_structured_skip() -> None:
    result = preflight_ansa_run(_request(env={}))

    assert result.status == "SKIPPED"
    assert result.error_code == "missing_ansa_executable"
    assert result.command == []


def test_command_builder_includes_sample_and_report_paths() -> None:
    executable = _fake_executable()
    request = _request(env={"ANSA_EXECUTABLE": executable.as_posix()})

    command = build_ansa_batch_command(request)

    assert command[:4] == [executable.resolve().as_posix(), "-b", "-nogui", "--confirm-license-agreement"]
    assert "-exec" in command
    assert any(item.startswith("load_script:") for item in command)
    payload = _decode_process_payload(command)
    assert payload["sample_dir"] == _sample_dir().resolve().as_posix()
    assert payload["manifest"] == (_sample_dir().resolve() / "labels" / "amg_manifest.json").as_posix()
    assert payload["execution_report"].endswith("ansa_execution_report.json")
    assert payload["quality_report"].endswith("ansa_quality_report.json")
    assert payload["batch_mesh_session"] == "AMG_SHELL_CONST_THICKNESS_V1"


def test_missing_manifest_raises_ansa_runner_error() -> None:
    executable = _fake_executable()

    with pytest.raises(AnsaRunnerError) as exc_info:
        preflight_ansa_run(_request(env={"ANSA_EXECUTABLE": executable.as_posix()}, with_manifest=False))
    assert exc_info.value.code == "missing_manifest"


def test_run_ansa_oracle_execute_false_does_not_call_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    executable = _fake_executable()
    request = _request(env={"ANSA_EXECUTABLE": executable.as_posix()})

    def fail_run(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("subprocess.run should not be called for execute=False")

    monkeypatch.setattr(ansa_runner.subprocess, "run", fail_run)

    result = run_ansa_oracle(request, execute=False)

    assert result.status == "DRY_RUN"
    assert result.command


def test_run_ansa_oracle_passes_timeout_to_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    executable = _fake_executable()
    request = _request(env={"ANSA_EXECUTABLE": executable.as_posix()}, timeout=7)
    calls: dict[str, object] = {}

    class Completed:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(command, capture_output, text, timeout, check):  # type: ignore[no-untyped-def]
        calls["command"] = command
        calls["capture_output"] = capture_output
        calls["text"] = text
        calls["timeout"] = timeout
        calls["check"] = check
        return Completed()

    monkeypatch.setattr(ansa_runner.subprocess, "run", fake_run)

    result = run_ansa_oracle(request, execute=True)

    assert result.status == "COMPLETED"
    assert result.stdout == "ok"
    assert calls["timeout"] == 7
    assert calls["capture_output"] is True
    assert calls["text"] is True
    assert calls["check"] is False
