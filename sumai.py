"""
SumAI: Answer a question based on a text document using the OpenAI API.
Document can be a .txt file or .json from pdfextract -t out.json.
Requires OPENAI_API_KEY in the environment.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path


def canonical_doc_filename(
    date_time: str | None, title: str | None, extension: str = ".json"
) -> str:
    """Build canonical document filename: YYYY-mm-dd_Document-title with words hyphenated."""
    # Date part: try to get YYYY-mm-dd from date_time, else today
    date_part = "0000-00-00"
    if date_time and date_time.strip():
        s = date_time.strip()
        # Try ISO-style first
        m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
        if m:
            y, mo, d = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
            date_part = f"{y}-{mo}-{d}"
        else:
            # Try (MM/)DD/YYYY or DD.MM.YYYY etc.
            m = re.search(r"(\d{4})", s)
            if m:
                date_part = f"{m.group(1)}-01-01"
            else:
                try:
                    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%m/%d/%Y", "%d.%m.%Y"):
                        try:
                            dt = datetime.strptime(s[:50], fmt)
                            date_part = dt.strftime("%Y-%m-%d")
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass
    if date_part == "0000-00-00":
        date_part = datetime.now().strftime("%Y-%m-%d")
    # Title part: hyphenate words, alphanumeric and hyphens only
    if title and title.strip():
        word = re.sub(r"[^\w\s-]", "", title.strip())
        word = re.sub(r"[-\s]+", "-", word).strip("-")
        title_part = word or "Untitled"
    else:
        title_part = "Untitled"
    return f"{date_part}_{title_part}{extension}"


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


def extract_meta_openai(
    document_text: str, model: str = "gpt-4o-mini"
) -> dict[str, str | None]:
    """Ask OpenAI to extract title, date-time, and 1-sentence summary. Returns dict with title, date_time, summary."""
    from openai import OpenAI

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    system = (
        "You are a precise assistant. Extract metadata from the document. "
        "Return ONLY a valid JSON object with exactly these keys (use null if not found): "
        '"title" (document title), "date_time" (document date/time as found in the text), '
        '"summary" (exactly one short sentence summarizing the document). No other text.'
    )
    user_content = f"Document:\n\n{document_text[:30000]}\n\n---\n\nReturn the JSON object only."
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
    )
    raw = (response.choices[0].message.content or "").strip()
    # Handle optional markdown code fence
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        out = json.loads(raw)
        return {
            "title": out.get("title") if out.get("title") else None,
            "date_time": out.get("date_time") if out.get("date_time") else None,
            "summary": out.get("summary") if out.get("summary") else None,
        }
    except json.JSONDecodeError:
        return {"title": None, "date_time": None, "summary": raw[:500] if raw else None}


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
  python sumai.py -i document.txt -e                    # extract title, date, 1-sentence summary
  python sumai.py -i document.txt -e -q "Summarize?"    # meta + question
  python sumai.py -i document.txt -ej                  # extract meta to document.json
  python sumai.py -i document.txt -ejc                 # extract meta to YYYY-mm-dd_Doc-title.json
  python sumai.py -i out.json -q "Summarize page 3" --model gpt-4o
  (Use pdfextract -t out.json to create JSON from a PDF first.)
        """,
    )
    parser.add_argument("-i", "--input", required=True, metavar="FILE", help="Document: .txt or .json (e.g. from pdfextract -t)")
    parser.add_argument("-q", "--question", metavar="Q", help="Question to answer from the document")
    parser.add_argument("-e", "--extract-meta", dest="extract_meta", action="store_true", help="Extract document title, date-time, and 1-sentence summary (print to stdout)")
    parser.add_argument("-ej", "--extract-json", dest="extract_json", action="store_true", help="Extract meta to JSON file: same dir as input, same stem with .json (e.g. doc.txt -> doc.json)")
    parser.add_argument("-ejc", "--extract-json-canonical", dest="extract_json_canonical", action="store_true", help="Extract meta to JSON with canonical name: YYYY-mm-dd_Document-title.json (words hyphenated)")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model (default: gpt-4o-mini)")
    args = parser.parse_args()

    if not args.extract_meta and not args.extract_json and not args.extract_json_canonical and not args.question:
        parser.error("At least one of -e/--extract-meta, -ej/--extract-json, -ejc/--extract-json-canonical, or -q/--question is required.")

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
        if args.extract_meta or args.extract_json or args.extract_json_canonical:
            meta = extract_meta_openai(doc_text, model=args.model)
            if args.extract_meta:
                print("Title:", meta["title"] or "(none)")
                print("Date/time:", meta["date_time"] or "(none)")
                print("Summary:", meta["summary"] or "(none)")
                if args.question:
                    print()
            if args.extract_json:
                inp = Path(args.input).resolve()
                json_path = inp.parent / f"{inp.stem}.json"
                json_path.write_text(
                    json.dumps({"title": meta["title"], "date_time": meta["date_time"], "summary": meta["summary"]}, indent=2),
                    encoding="utf-8",
                )
                print(f"Wrote: {json_path}", file=sys.stderr)
            if args.extract_json_canonical:
                inp = Path(args.input).resolve()
                name = canonical_doc_filename(meta["date_time"], meta["title"], ".json")
                json_path = inp.parent / name
                json_path.write_text(
                    json.dumps({"title": meta["title"], "date_time": meta["date_time"], "summary": meta["summary"]}, indent=2),
                    encoding="utf-8",
                )
                print(f"Wrote: {json_path}", file=sys.stderr)
        if args.question:
            answer = ask_openai(doc_text, args.question, model=args.model)
            print(answer)
    except Exception as e:
        print(f"Error calling OpenAI: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
