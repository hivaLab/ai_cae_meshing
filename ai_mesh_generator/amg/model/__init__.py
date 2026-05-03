"""Model namespace for AMG."""

from ai_mesh_generator.amg.model.graph_model import (
    AmgGraphModel,
    AmgModelOutput,
    GraphBatch,
    ModelDimensions,
    build_graph_batch,
)
from ai_mesh_generator.amg.model.projector import (
    ACTION_NAMES,
    AmgModelError,
    ProjectedModelOutput,
    apply_action_mask,
    project_model_output,
)

__all__ = [
    "ACTION_NAMES",
    "AmgGraphModel",
    "AmgModelError",
    "AmgModelOutput",
    "GraphBatch",
    "ModelDimensions",
    "ProjectedModelOutput",
    "apply_action_mask",
    "build_graph_batch",
    "project_model_output",
]
