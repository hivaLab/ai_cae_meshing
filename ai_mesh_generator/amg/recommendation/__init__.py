"""AMG quality recommendation entrypoints."""

__all__ = [
    "AmgQualityRecommendationError",
    "CandidateManifestScore",
    "QualityRecommendationConfig",
    "QualityRecommendationResult",
    "QualityRecommendationSampleResult",
    "AmgFreshProposalError",
    "FreshCandidateManifest",
    "FreshProposalConfig",
    "FreshProposalResult",
    "FreshProposalSampleResult",
    "generate_fresh_candidate_manifests",
    "load_candidate_manifests",
    "load_quality_ranker",
    "main",
    "run_fresh_quality_proposal",
    "run_quality_recommendation",
    "score_fresh_candidates",
    "score_candidate_manifests",
    "select_recommendation_samples",
]


def __getattr__(name: str):
    fresh_names = {
        "AmgFreshProposalError",
        "FreshCandidateManifest",
        "FreshProposalConfig",
        "FreshProposalResult",
        "FreshProposalSampleResult",
        "generate_fresh_candidate_manifests",
        "run_fresh_quality_proposal",
        "score_fresh_candidates",
    }
    if name in fresh_names:
        import importlib

        module = importlib.import_module("ai_mesh_generator.amg.recommendation.fresh")
        return getattr(module, name)
    if name in __all__:
        import importlib

        module = importlib.import_module("ai_mesh_generator.amg.recommendation.quality")
        return getattr(module, name)
    raise AttributeError(name)
