"""Training smoke namespace for AMG."""

from ai_mesh_generator.amg.training.real import (
    AmgRealTrainingError,
    ManifestSupervisionTargets,
    RealTrainingConfig,
    RealTrainingResult,
    build_manifest_supervision_targets,
    compute_manifest_supervised_loss,
    main,
    run_real_dataset_training,
    validate_real_training_dataset,
)
from ai_mesh_generator.amg.training.smoke import (
    AmgTrainingSmokeError,
    SmokeLossBreakdown,
    SmokeTargets,
    SmokeTrainingResult,
    build_smoke_targets,
    compute_smoke_loss,
    load_smoke_checkpoint,
    run_training_smoke,
    save_smoke_checkpoint,
)

__all__ = [
    "AmgRealTrainingError",
    "AmgTrainingSmokeError",
    "ManifestSupervisionTargets",
    "RealTrainingConfig",
    "RealTrainingResult",
    "SmokeLossBreakdown",
    "SmokeTargets",
    "SmokeTrainingResult",
    "build_manifest_supervision_targets",
    "build_smoke_targets",
    "compute_manifest_supervised_loss",
    "compute_smoke_loss",
    "load_smoke_checkpoint",
    "main",
    "run_real_dataset_training",
    "run_training_smoke",
    "save_smoke_checkpoint",
    "validate_real_training_dataset",
]
