from __future__ import annotations


def failure_risks(assembly: dict) -> list[dict]:
    defects_by_part = {defect["part_uid"]: defect for defect in assembly.get("defects", [])}
    risks = []
    for part in assembly["parts"]:
        defect = defects_by_part.get(part["part_uid"])
        risks.append(
            {
                "part_uid": part["part_uid"],
                "risk": round(float(defect["severity"]) if defect else 0.05, 4),
                "reason": defect["defect_type"] if defect else "nominal",
            }
        )
    return risks
