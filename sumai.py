"""
SumAI: Answer a question based on a text document using the OpenAI API.
Document can be a .txt file or .json from pdfextract -t out.json.
Requires OPENAI_API_KEY in the environment.
"""

import argparse
import json
import os
import sys
from pathlib import Path


def load_document(path: Path) -> str:
    """Load document text from .txt or .json (pdfextract -t output)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "pages" in data:
            return "\n\n".join(
                p.get("text", "") for p in data["pages"]
            ).strip()
        if isinstance(data, list):
            return "\n\n".join(
                p.get("text", p) if isinstance(p, dict) else str(p) for p in data
            ).strip()
        return json.dumps(data, ensure_ascii=False)
    # .txt or any other: read as plain text
    return path.read_text(encoding="utf-8").strip()


def ask_openai(document_text: str, question: str, model: str = "gpt-4o-mini") -> str:
    """Send document + question to OpenAI Chat Completions; return assistant reply."""
    from openai import OpenAI

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    system = (
        "You are a helpful assistant. Answer the user's question based only on the provided document. "
        "If the document does not contain enough information, say so. Keep answers concise."
    )
    user_content = f"Document:\n\n{document_text}\n\n---\n\nQuestion: {question}"
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
    )
    return response.choices[0].message.content or ""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Answer a question based on a text document (OpenAI API).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Requires OPENAI_API_KEY in the environment.

Examples:
  python sumai.py -i document.txt -q "What is the main conclusion?"
  python sumai.py -i out.json -q "Summarize page 3" --model gpt-4o
  (Use pdfextract -t out.json to create JSON from a PDF first.)
        """,
    )
    parser.add_argument("-i", "--input", required=True, metavar="FILE", help="Document: .txt or .json (e.g. from pdfextract -t)")
    parser.add_argument("-q", "--question", required=True, metavar="Q", help="Question to answer from the document")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model (default: gpt-4o-mini)")
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

    try:
        doc_text = load_document(Path(args.input))
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading document: {e}", file=sys.stderr)
        sys.exit(1)

    if not doc_text:
        print("Error: Document is empty.", file=sys.stderr)
        sys.exit(1)

    try:
        answer = ask_openai(doc_text, args.question, model=args.model)
        print(answer)
    except Exception as e:
        print(f"Error calling OpenAI: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
