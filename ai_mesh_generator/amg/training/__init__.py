"""Training smoke namespace for AMG."""

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
    "AmgTrainingSmokeError",
    "SmokeLossBreakdown",
    "SmokeTargets",
    "SmokeTrainingResult",
    "build_smoke_targets",
    "compute_smoke_loss",
    "load_smoke_checkpoint",
    "run_training_smoke",
    "save_smoke_checkpoint",
]
