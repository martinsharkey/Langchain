"""
RAG Guard — CLI tool for querying the library documentation RAG.

Before writing any vectorbt or optuna code, developers must query this tool
to confirm the correct API. See CODING_RULES.md for the full rule set.

Usage:
    python -m scripts.qmmp.rag_guard "Portfolio.from_signals stop loss trailing"
    python -m scripts.qmmp.rag_guard "TPE sampler suggest_float" --collection optuna_docs
    python -m scripts.qmmp.rag_guard "IndicatorFactory param sweep" --collection vectorbt_docs --n 3

Collections:
    vectorbt_docs   vectorbt Portfolio, IndicatorFactory, splitters, records
    optuna_docs     Optuna create_study, Trial API, samplers, pruners, RDB storage
    ta_libs_docs    ta, pandas-ta, ta-lib indicator references
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path so src imports work
_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_root))

from src.learning.docs_rag import DocsRAG, _VALID_COLLECTIONS


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query the library documentation RAG before writing vectorbt/optuna code.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "query",
        help='Question or keyword phrase, e.g. "Portfolio.from_signals sl_stop trailing"',
    )
    parser.add_argument(
        "--collection",
        default="vectorbt_docs",
        choices=list(_VALID_COLLECTIONS),
        help="Which documentation collection to search (default: vectorbt_docs)",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=5,
        help="Number of results to return (default: 5)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Query all three collections and show top 3 from each",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild ChromaDB collections from docs/lib_docs/ before querying",
    )

    args = parser.parse_args()

    rag = DocsRAG()

    if args.rebuild:
        print("Rebuilding ChromaDB collections from docs/lib_docs/ ...")
        counts = DocsRAG.build_collections()
        for name, count in counts.items():
            print(f"  {name}: {count} chunks")
        print()

    # Verify collections are populated
    stats = rag.collection_stats()
    empty = [name for name, count in stats.items() if count == 0]
    if empty:
        print(f"WARNING: These collections are empty: {empty}")
        print("Run with --rebuild to build them from docs/lib_docs/")
        print()

    print(f'Query: "{args.query}"')
    print(f"Collection: {args.collection if not args.all else 'all'}")
    print("=" * 70)

    if args.all:
        results_by_col = rag.query_all(args.query, n=3)
        for col_name, results in results_by_col.items():
            print(f"\n── {col_name} ──")
            if not results:
                print("  (no results)")
                continue
            for i, r in enumerate(results, 1):
                print(f"\n[{i}] Source: {r['source']}  Score: {r['score']}")
                print(r["text"][:500])
                if len(r["text"]) > 500:
                    print("  ...")
    else:
        results = rag.query(args.query, collection=args.collection, n=args.n)
        if not results:
            print("No results. Try --rebuild if collections are empty.")
        for i, r in enumerate(results, 1):
            print(f"\n[{i}] Source: {r['source']}  Score: {r['score']}")
            print(r["text"][:600])
            if len(r["text"]) > 600:
                print("  ...")

    print("\n" + "=" * 70)
    print("Paste the most relevant result into your PR description as evidence")
    print("you checked the real API before writing code. See CODING_RULES.md.")


if __name__ == "__main__":
    main()
