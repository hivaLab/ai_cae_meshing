from __future__ import annotations

from pathlib import Path


def write_procedural_step(path: Path | str, sample_id: str, part_names: list[str]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = [
        "ISO-10303-21;",
        "HEADER;",
        f"FILE_DESCRIPTION(('Procedural CAE mesh sample {sample_id}'),'2;1');",
        "FILE_SCHEMA(('AP242_MANAGED_MODEL_BASED_3D_ENGINEERING_MIM_LF'));",
        "ENDSEC;",
        "DATA;",
    ]
    for index, name in enumerate(part_names, start=1):
        body.append(f"#{index}=PRODUCT('{name}','{name}','procedural placeholder',());")
    body.extend(["ENDSEC;", "END-ISO-10303-21;"])
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    return path
