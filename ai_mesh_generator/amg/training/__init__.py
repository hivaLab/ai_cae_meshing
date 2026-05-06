"""AMG v2 training namespace."""

from ai_mesh_generator.amg.training.part_classifier import train_part_classifier_from_dataset
from ai_mesh_generator.amg.training.segmentation import train_entity_segmentation_from_dataset
from ai_mesh_generator.amg.training.size_field import train_size_field_model

__all__ = [
    "train_entity_segmentation_from_dataset",
    "train_part_classifier_from_dataset",
    "train_size_field_model",
]
