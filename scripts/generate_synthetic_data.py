from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.synthetic_data import GenerationConfig, build_corpus, write_corpus  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the canonical KRAKEN synthetic corpus.")
    parser.add_argument("--generation", default="northstar-v1")
    parser.add_argument("--seed", type=int, default=240831)
    parser.add_argument("--output-root", type=Path, default=ROOT / "data")
    parser.add_argument("--check", action="store_true", help="Validate without writing files.")
    args = parser.parse_args()

    corpus = build_corpus(GenerationConfig(generation=args.generation, seed=args.seed))
    if args.check:
        assert corpus.manifest is not None
        print(
            f"synthetic corpus valid: generation={corpus.manifest.generation} "
            f"tickets={len(corpus.tickets)} documents={len(corpus.documents)} "
            f"scenarios={len(corpus.scenarios)}"
        )
        return

    written = write_corpus(corpus, data_root=args.output_root.resolve())
    print(f"synthetic corpus written: {len(written)} files")
    print(f"manifest: {args.output_root.resolve() / 'synthetic' / 'manifest.json'}")


if __name__ == "__main__":
    main()
