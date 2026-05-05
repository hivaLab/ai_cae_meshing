"""AMG real-pipeline benchmark reporting."""

from ai_mesh_generator.amg.benchmark.real_pipeline import (
    AmgBenchmarkReportError,
    build_real_pipeline_benchmark_report,
    main,
    write_real_pipeline_benchmark_report,
)

__all__ = [
    "AmgBenchmarkReportError",
    "AmgQualityBenchmarkError",
    "build_real_pipeline_benchmark_report",
    "build_quality_benchmark_report",
    "main",
    "quality_main",
    "write_real_pipeline_benchmark_report",
    "write_quality_benchmark_report",
    "AmgRecommendationBenchmarkError",
    "build_recommendation_benchmark_report",
    "recommendation_main",
    "write_recommendation_benchmark_report",
]


def __getattr__(name: str):
    if name in {
        "AmgQualityBenchmarkError",
        "build_quality_benchmark_report",
        "quality_main",
        "write_quality_benchmark_report",
    }:
        import importlib

        module = importlib.import_module("ai_mesh_generator.amg.benchmark.quality")
        if name == "quality_main":
            return module.main
        return getattr(module, name)
    if name in {
        "AmgRecommendationBenchmarkError",
        "build_recommendation_benchmark_report",
        "recommendation_main",
        "write_recommendation_benchmark_report",
    }:
        import importlib

        module = importlib.import_module("ai_mesh_generator.amg.benchmark.recommendation")
        if name == "recommendation_main":
            return module.main
        return getattr(module, name)
    raise AttributeError(name)
