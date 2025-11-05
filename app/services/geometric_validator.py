"""Validador de plausibilidade geométrica para elementos BIM."""

import structlog

from app.services.hallucination_mitigation import DetectedElement

logger = structlog.get_logger(__name__)


class GeometricValidator:
    STRUCTURAL_DEPENDENCIES = {
        "beam": ["column", "wall"],
        "slab": ["beam", "wall", "column"],
    }
    REQUIRES_FOUNDATION = ["column", "wall"]
    CONSTRUCTION_SEQUENCE = {
        "foundation": 1, "footing": 1, "pile": 1,
        "column": 2, "wall": 2,
        "beam": 3, "slab": 3,
        "roof": 4, "finishing": 5,
    }

    def validate_elements(self, detected_elements: list[DetectedElement], strict_mode: bool = False) -> dict:
        if not detected_elements:
            return {"is_plausible": True, "issues": [], "confidence_penalty": 0.0,
                    "validated_elements": [], "suspicious_elements": []}

        types_detected = {elem.element_type.lower() for elem in detected_elements}
        issues = []
        
        issues.extend(self._validate_structural_support(types_detected))
        issues.extend(self._validate_foundation(types_detected, strict_mode))
        issues.extend(self._validate_construction_sequence(detected_elements))

        high_severity = sum(1 for i in issues if i["severity"] == "HIGH")
        confidence_penalty = min(high_severity * 0.15 + sum(1 for i in issues if i["severity"] == "MEDIUM") * 0.05, 0.5)
        
        suspicious = self._identify_suspicious(detected_elements, issues)
        validated = [e for e in detected_elements if e not in suspicious]

        return {
            "is_plausible": high_severity == 0,
            "issues": issues,
            "confidence_penalty": confidence_penalty,
            "validated_elements": validated,
            "suspicious_elements": suspicious,
        }

    def _validate_structural_support(self, types_detected: set[str]) -> list[dict]:
        issues = []
        for elem_type, required_supports in self.STRUCTURAL_DEPENDENCIES.items():
            if elem_type in types_detected and not any(s in types_detected for s in required_supports):
                issues.append({
                    "rule": "missing_structural_support",
                    "severity": "HIGH",
                    "element_type": elem_type,
                    "message": f"{elem_type} without support ({', '.join(required_supports)})",
                    "likely_hallucination": True,
                })
        return issues

    def _validate_foundation(self, types_detected: set[str], strict_mode: bool) -> list[dict]:
        issues = []
        has_vertical = any(t in types_detected for t in self.REQUIRES_FOUNDATION)
        has_foundation = any(t in types_detected for t in {"foundation", "footing", "pile", "slab"})
        
        if has_vertical and not has_foundation:
            issues.append({
                "rule": "missing_foundation",
                "severity": "HIGH" if strict_mode else "MEDIUM",
                "message": "Vertical elements without foundation",
                "likely_hallucination": False,
            })
        return issues

    def _validate_construction_sequence(self, elements: list[DetectedElement]) -> list[dict]:
        issues = []
        status_by_type = {}
        for elem in elements:
            t, s = elem.element_type.lower(), elem.status.lower()
            status_by_type.setdefault(t, []).append(s)

        for elem_type, statuses in status_by_type.items():
            if "completed" not in statuses:
                continue
            current_order = self.CONSTRUCTION_SEQUENCE.get(elem_type, 999)
            for earlier_type, earlier_order in self.CONSTRUCTION_SEQUENCE.items():
                if earlier_order < current_order and earlier_type in status_by_type:
                    earlier_statuses = status_by_type[earlier_type]
                    if "not_started" in earlier_statuses and "completed" not in earlier_statuses:
                        issues.append({
                            "rule": "invalid_sequence",
                            "severity": "HIGH",
                            "message": f"{elem_type} completed but {earlier_type} not started",
                            "likely_hallucination": True,
                        })
        return issues

    def _identify_suspicious(self, elements: list[DetectedElement], issues: list[dict]) -> list[DetectedElement]:
        suspicious_types = {i["element_type"] for i in issues 
                           if i["severity"] == "HIGH" and i.get("likely_hallucination")}
        return [e for e in elements if e.element_type.lower() in suspicious_types and e.confidence in ["MEDIUM", "LOW"]]
