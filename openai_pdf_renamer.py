########### PYTHON
# Script Title: OpenAI PDF Smart Renamer
# Script Description: Rename and update PDF files in a directory using OpenAI's Chat API to generate structured metadata (author, title, pubdate) from PDF text. Ensures valid filenames and updates embedded PDF metadata.
# Script Author: myPyAI + Naveen Srivatsav
# Last Updated: 20240604
# TLA+ Abstract:
# """
# tla ---- MODULE openai_pdf_renamer ----
# VARIABLES pdf_files, extracted_texts, ai_metadata, renamed_pdfs
# Init == pdf_files \in Directory /\ extracted_texts = <<>> /\ ai_metadata = <<>> /\ renamed_pdfs = {}
# Next == \E file \in pdf_files:
#      /\ extracted_texts' = ExtractText(file)
#      /\ ai_metadata' = QueryLLM(extracted_texts)
#      /\ IF Valid(ai_metadata') THEN
#           renamed_pdfs' = RenameAndUpdate(renamed_pdfs, file, ai_metadata')
#         ELSE
#           renamed_pdfs' = NoChange(renamed_pdfs, file)
# Success == \A f \in pdf_files: FileIsNamedAndTagged(f)
# ----
# """
# Library/Design notes: Uses OpenAI's gpt-3.5-turbo for fast, cost-effective LLM inference. PDF IO by PyPDF2; .env-driven config for secure API keys. Modular design for clarity, diagnostics, future backend swaps, and easy extension.
###########

# To run: pip install openai PyPDF2 python-dotenv
import os  # Standard: Filesystem, env
import re  # Standard: Validation/sanitization
import json  # Standard: Parsing/structuring LLM output
from pathlib import Path  # Standard: Modern filesystem
from typing import Optional, Dict  # Standard: Type hints for clarity

# Third-party packages
import openai  # LLM backend
from PyPDF2 import PdfReader, PdfWriter  # PDF handling
from dotenv import load_dotenv  # Secure env config

from datetime import datetime  # For fallback years

# INGREDIENTS:
# - Standard: os, re, json, pathlib, typing, datetime
# - Third-party: openai, PyPDF2, python-dotenv

def load_openai_client(api_var: str = "OPENAI_API_KEY"):
    """
    Big-picture: Loads .env (if present), retrieves the OpenAI API key, and configures the openai Python package.
    Inputs: Environment variable name (default 'OPENAI_API_KEY')
    Outputs: None (sets global openai.api_key)
    Role: Ensures reproducible, secure LLM API calls using best-practice key storage.
    """
    load_dotenv()
    key = os.getenv(api_var)
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set. Please add it to .env or env.")
    openai.api_key = key

def extract_text_from_pdf(pdf_path: Path, max_pages: int = 5) -> Optional[str]:
    """
    Big-picture: Extracts text from the first few pages of a PDF (only accessible text, no OCR).
    Inputs: pdf_path (Path), max_pages (pages to consider for richer context).
    Outputs: Extracted text as a single string, or None if not text-extractable.
    Role: Prepares LLM input with enough context for robust metadata inference.
    """
    try:
        reader = PdfReader(str(pdf_path))
        out = ""
        for page in reader.pages[:max_pages]:
            t = page.extract_text()
            if t:
                out += t
        return out.strip() if out else None
    except Exception as e:
        print(f"PDF extraction failed ({pdf_path.name}): {e}")
        return None

SYSTEM_PROMPT = (
    "You are a librarian interested in the organization of knowledge. "
    "You assist in renaming digital files to build a perfect library. "
    "Only respond in JSON with fields: author, title, pubdate as CamelCase strings. Use spaces and not underscores between words within fields."
    "If unsure, print 'Various' for author or 'Unknown' for title. pubdate is four-digit year."
)

def build_user_msg(text: str) -> str:
    return (
        "Given the following text, guess probable author (with a preference for institutional acronyms over individuals), title, and publication year. "
        "Format like: OrgA & OrgB & Jane Smith - The Document Title- Subtitles (2023). "
        "Strictly JSON: {'author':'', 'title':'', 'pubdate':''}. "
        "----\n"
        f"{text[:3000]}\n"
        "----"
    )

def query_llm_for_metadata(text: str, retries: int = 2, model: str = "gpt-4.1-mini") -> Optional[Dict[str, str]]:
    """
    Big-picture: Call OpenAI chat endpoint with extracted text prompt, returning parsed JSON with author/title/pubdate.
    Inputs: Extracted text (str), retry count, OpenAI model.
    Outputs: Dict with metadata keys, or None if API/parse error.
    Role: Bottleneck for all LLM-based reasoning in workflow.
    """
    user_msg = build_user_msg(text)
    for attempt in range(retries):
        try:
            resp = openai.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg}
                ],
                max_tokens=128,
                temperature=0.3,
            )
            raw = resp.choices[0].message.content.strip()
            # Try to parse as JSON (allow code block)
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.DOTALL)
            data = match.group(1) if match else raw
            # Remove any markdown or commentary lines before/after the JSON
            data = re.sub(r'^.*?(\{)', r'\1', data, flags=re.DOTALL)
            data = re.sub(r'(\}).*?$', r'\1', data, flags=re.DOTALL)
            metadata = json.loads(data)
            # Field reliability check
            if (
                metadata.get("title", "").strip().lower() == "unknown" or
                metadata.get("author", "").strip().lower() in {"unknown", "various"}
            ):
                return None
            return metadata
        except Exception as e:
            print(f"OpenAI API error / JSON parse error: {e}")
            import time
            time.sleep(2)
    return None

def clean_filename(raw: str, max_length: int = 128) -> str:
    """
    Big-picture: Sanitizes and compresses string for OS-safe filenames.
    Inputs: raw string (suggested filename)
    Outputs: Cleaned, truncated candidate filename (w/o .pdf)
    Role: Ensures cross-platform safety, dedupe, and human readability.
    """
    name = re.sub(r'[\/:*?"<>|]', '', raw)
    name = name.replace(' ', '_')
    name = re.sub(r'_{2,}', '_', name)
    return name[:max_length].strip('_')

def find_unique_pdf_path(base: Path, candidate_name: str) -> Path:
    """
    Big-picture: Given a directory and candidate filename, ensure unique final path (avoid overwrite).
    Inputs: base (current file path), candidate_name (no .pdf), returns Path
    Outputs: Unique destination Path
    Role: Atomic, idempotent file renaming
    """
    directory = base.parent
    new_path = directory / f"{candidate_name}.pdf"
    counter = 1
    while new_path.exists():
        new_path = directory / f"{candidate_name}_{counter}.pdf"
        counter += 1
    return new_path

def update_pdf_metadata(src: Path, title: str, author: str, pubdate: str) -> bool:
    """
    Big-picture: Safely update PDF internal Title/Author/CreationDate tags.
    Inputs: Source PDF path, title, author, pubdate (year string)
    Outputs: Bool (success)
    Role: Enables long-term searchability/discoverability within docs.
    """
    try:
        reader = PdfReader(str(src))
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        year = str(pubdate) if pubdate.isdigit() else str(datetime.now().year)
        metadata = {
            "/Title": title,
            "/Author": author,
            "/CreationDate": f"D:{year}0101000000Z"
        }
        writer.add_metadata(metadata)
        temp_path = src.with_suffix('.temp.pdf')
        with open(temp_path, 'wb') as f:
            writer.write(f)
        temp_path.replace(src)
        return True
    except Exception as e:
        print(f"Failed to update metadata for {src.name}: {e}")
        return False

def rename_pdf(pdf_path: Path, clean_base: str) -> Optional[Path]:
    """
    Big-picture: Rename a PDF, ensuring full uniqueness.
    Inputs: pdf_path (original), clean_base (string, no .pdf)
    Outputs: New Path on success, None on error
    Role: Moves file, fulfills rename semantics for modular testability.
    """
    dest_path = find_unique_pdf_path(pdf_path, clean_base)
    try:
        pdf_path.rename(dest_path)
        print(f"Renamed: {pdf_path.name} → {dest_path.name}")
        return dest_path
    except Exception as e:
        print(f"Failed to rename {pdf_path.name}: {e}")
        return None

def process_pdf(pdf_path: Path) -> None:
    """
    Big-picture: Orchestrates single PDF workflow: extract → LLM guess → decide → update metadata → move.
    Inputs: PDF path
    Outputs: None
    Role: Encapsulates all business logic for one PDF (testable unit).
    """
    text = extract_text_from_pdf(pdf_path)
    if not text:
        print(f"Could not extract text from {pdf_path.name}. Skipping.")
        return
    metadata = query_llm_for_metadata(text)
    if not metadata:
        print(f"AI suggestion unreliable or unavailable. Skipping '{pdf_path.name}'.")
        return
    author = metadata.get("author", "Unknown")
    title = metadata.get("title", "Unknown")
    pubdate = metadata.get("pubdate", str(datetime.now().year))
    base_name = f"{author} - {title} ({pubdate})"
    clean_base = clean_filename(base_name)
    # Always update metadata, regardless of final renaming
    update_pdf_metadata(pdf_path, clean_filename(title), clean_filename(author), pubdate)
    rename_pdf(pdf_path, clean_base)

def main():
    """
    Big-picture:
    1. Prompt user for target directory.
    2. List and sort all PDFs (recent first) in directory.
    3. For each: extract → AI guess → check → update metadata → rename.
    4. Print progress, errors, and finish statement.
    Rationale: Orchestrates the full batch renaming process; easy to adapt for batch/pipeline execution.
    """
    try:
        load_openai_client()
    except Exception as e:
        print(f"Setup error: {e}")
        return
    dir_input = input("Please enter the directory containing the PDFs: ").strip()
    directory = Path(dir_input).expanduser().resolve()
    if not directory.is_dir():
        print("Invalid directory. Exiting.")
        return
    pdf_files = sorted(directory.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not pdf_files:
        print("No PDF files found in directory.")
        return
    for pdf_path in pdf_files:
        print(f"\nProcessing: {pdf_path.name}")
        process_pdf(pdf_path)
    print("Finished processing all PDFs!")

if __name__ == "__main__":
    main()
