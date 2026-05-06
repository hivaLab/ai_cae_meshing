"""AMG v2 training namespace."""

from ai_mesh_generator.amg.training.part_classifier import train_part_classifier_from_dataset
from ai_mesh_generator.amg.training.quality_surrogate import train_quality_surrogate_from_dataset
from ai_mesh_generator.amg.training.segmentation import train_entity_segmentation_from_dataset

__all__ = [
    "train_entity_segmentation_from_dataset",
    "train_part_classifier_from_dataset",
    "train_quality_surrogate_from_dataset",
]
