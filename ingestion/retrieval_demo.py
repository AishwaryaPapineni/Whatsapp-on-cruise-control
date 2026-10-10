#!/usr/bin/env python3
"""Run readable retrieval checks against the relationship-specific histories."""

import argparse
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.constants import RELATIONSHIPS  # noqa: E402
from ingestion.embedder import get_client, get_embedder  # noqa: E402

RESULTS_PATH = ROOT / "private" / "retrieval_results.txt"  # contains your real chats -> git-ignored
SAMPLE_QUERIES = {
    "family": (
        "Khana kha liya?",
        "Reached home safely",
        "Good morning beta",
    ),
    "friend": (
        "yaar kal free hai kya",
        "That was really fun, let's do it again.",
        "Are you free this evening?",
    ),
    "professional": (
        "Could you share an update on the project timeline?",
        "Please confirm the meeting time and next steps.",
        "I will review this and get back to you shortly.",
    ),
    "unknown": (
        "Can you send me an update?",
        "What time should we meet?",
        "Thanks, I will check and let you know.",
    ),
}


class Tee:
    """Write the report to the terminal and the saved results file together."""

    def __init__(self, terminal, report_file):
        self.terminal = terminal
        self.report_file = report_file

    def write(self, text: str) -> int:
        self.terminal.write(text)
        self.report_file.write(text)
        self.report_file.flush()
        return len(text)

    def flush(self) -> None:
        self.terminal.flush()
        self.report_file.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Demo retrieval from relationship-specific Chroma histories.")
    parser.add_argument(
        "--relationship",
        choices=("all", *RELATIONSHIPS),
        default="all",
        help="Relationship collection to search (default: all four).",
    )
    parser.add_argument(
        "--query",
        help="Use one query for each selected relationship instead of built-in samples.",
    )
    return parser


def selected_relationships(relationship: str) -> tuple[str, ...]:
    return RELATIONSHIPS if relationship == "all" else (relationship,)


def print_results(relationship: str, query: str, result: dict) -> bool:
    distances = result.get("distances", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]

    print("\n" + "=" * 72)
    print(f"Relationship: {relationship}")
    print(f"Test query: {query}")
    print("=" * 72)
    for result_number, (distance, document, metadata) in enumerate(
        zip(distances, documents, metadatas), start=1
    ):
        print("---")
        print(f"Result {result_number} | distance: {distance:.6f}")
        print(f"Their message: {document}  [{metadata.get('conversation_id', '')}]")
        print(f"My reply: {metadata.get('my_reply', '')}")
        print(f"Timestamp: {metadata.get('timestamp', '')}")
    print("---")
    return all(first <= second for first, second in zip(distances, distances[1:]))


def run_demo(args: argparse.Namespace) -> None:
    model = get_embedder()
    client = get_client()
    print(f"Embedder: {model.name}")
    relationships = selected_relationships(args.relationship)
    sanity_checks: dict[str, list[bool]] = {relationship: [] for relationship in relationships}

    for relationship in relationships:
        collection_name = f"history_{relationship}"
        try:
            collection = client.get_collection(collection_name)
        except Exception:
            print(f"⚠\ufe0f no data in {collection_name}, skipping")
            continue
        document_count = collection.count()
        if document_count == 0:
            print(f"⚠\ufe0f no data in {collection_name}, skipping")
            continue

        queries = (args.query,) if args.query else SAMPLE_QUERIES[relationship]
        for query in queries:
            query_embedding = list(model.encode([query], show_progress_bar=False)[0])
            result = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(3, document_count),
                include=["documents", "metadatas", "distances"],
            )
            sanity_checks[relationship].append(print_results(relationship, query, result))

    print("\nSanity checks:")
    for relationship in relationships:
        checks = sanity_checks[relationship]
        if not checks:
            print(f"- {relationship}: skipped (no data)")
        elif all(checks):
            print(f"- {relationship}: distances monotonically increasing (expected/good)")
        else:
            print(f"- {relationship}: distances not monotonically increasing (worth a second look)")


def main() -> None:
    args = build_parser().parse_args()
    RESULTS_PATH.parent.mkdir(exist_ok=True)
    with RESULTS_PATH.open("w", encoding="utf-8") as report_file:
        with redirect_stdout(Tee(sys.stdout, report_file)):
            run_demo(args)
    print(f"\nSaved retrieval results to {RESULTS_PATH}")


if __name__ == "__main__":
    main()