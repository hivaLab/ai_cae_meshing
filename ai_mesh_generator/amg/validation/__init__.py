"""Validation namespace for AMG."""

from ai_mesh_generator.amg.validation.input_validation import (
    AmgInputValidationError,
    AmgInputValidationResult,
    ValidationCheckResult,
    build_out_of_scope_manifest,
    validate_amg_inputs,
    write_out_of_scope_manifest,
)

__all__ = [
    "AmgInputValidationError",
    "AmgInputValidationResult",
    "ValidationCheckResult",
    "build_out_of_scope_manifest",
    "validate_amg_inputs",
    "write_out_of_scope_manifest",
]
