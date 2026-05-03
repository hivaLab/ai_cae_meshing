"""AMG real inference namespace."""

from ai_mesh_generator.amg.inference.real_mesh import (
    AmgRealInferenceError,
    PredictedManifestResult,
    RealInferenceConfig,
    RealInferenceResult,
    RealMeshSampleResult,
    build_predicted_amg_manifest,
    load_trained_checkpoint,
    main,
    run_real_mesh_inference,
    select_inference_samples,
)

__all__ = [
    "AmgRealInferenceError",
    "PredictedManifestResult",
    "RealInferenceConfig",
    "RealInferenceResult",
    "RealMeshSampleResult",
    "build_predicted_amg_manifest",
    "load_trained_checkpoint",
    "main",
    "run_real_mesh_inference",
    "select_inference_samples",
]
