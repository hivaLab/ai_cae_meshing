"""AMG quality recommendation entrypoints."""

__all__ = [
    "AmgQualityRecommendationError",
    "CandidateManifestScore",
    "QualityRecommendationConfig",
    "QualityRecommendationResult",
    "QualityRecommendationSampleResult",
    "load_candidate_manifests",
    "load_quality_ranker",
    "main",
    "run_quality_recommendation",
    "score_candidate_manifests",
    "select_recommendation_samples",
]


def __getattr__(name: str):
    if name in __all__:
        import importlib

        module = importlib.import_module("ai_mesh_generator.amg.recommendation.quality")
        return getattr(module, name)
    raise AttributeError(name)
