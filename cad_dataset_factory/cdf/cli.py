"""Compatibility shim for the CDF v2 entity CLI.

The old manifest-oriented ``cdf`` command is no longer a primary entrypoint.  The
implementation delegates to ``cdf-entity`` so old invocations fail or succeed according
to the new entity pipeline, not the legacy feature-action pipeline.
"""

from __future__ import annotations

import sys
from typing import Sequence

from cad_dataset_factory.cdf.entity_cli import main as entity_main


def main(argv: Sequence[str] | None = None) -> int:
    return entity_main(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
