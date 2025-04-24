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
    "You are an expert librarian specializing in digital knowledge management, renowned for your meticulous approach to naming, organizing, and ensuring the discoverability of electronic resources. In your process, you practice analytical cross-referencing, triangulating key bibliographic details from multiple points within a document (title page, copyright, TOC, citation instructions). Your philosophy is driven by optimally balancing user searchability (discoverability), source traceability (sourceability), and archival order. You bring a systems view: every filename you craft is an intentional node in a vast, navigable digital knowledge ecosystem, shaped to maximize both present retrieval and future relevance."
    "Upon receiving the first ten pages of raw text from a PDF, your task is to accurately infer and assemble three bibliographic details for effective PDF file naming. Your priority is capturing the full title and subtitle of the document. Institutional/individual author as a secondary priority and year of publication as a tertiary priority."
    "Title: Extract the complete, official title (including subtitle), prioritizing accuracy and specificity. Cross-check its consistency by locating it on the title page, copyright page, table of contents, and in citation guidance sections."
    "Author/Institution: Determine the primary institution(s) or lead author(s). Give preference to institutional names over individuals. If multiple institutions are listed, include a maximum of three (joined by \"&\"). For individual authors in journal papers, use the lead author’s name followed by \"etal\" if appropriate."
    "Year of Publication: Infer the most likely year (including month if present for increased precision), also validated across several mentions in the document."
    "Structure the filename as: [Institution(s) or Author] - [Full Title] ([Year])"
    "Example: OECD & MissionLab - Harnessing mission governance to achieve national climate targets (2025)"
    "Prioritize institutions and specifically use their most recognisable acronyms. For example, Harvard University should be abbreviated to HarvardU, International Monetary Fund should be labelled IMF, Bank of America should be shortened to BoA and so on. If there are more than two instituions, mention only the primary institution (acronym preferred always) following by '& Various'."
    "Only use individual names if institutions are unclear/not primary. For single-author papers, include the full name(s); for two or more authors, use the lead name and \"etal\"."
    "Month or season in the date is included if available, else use just the year."
    "Always use an ampersand (&) to separate institutions (maximum of 3) and 'etal' to indicate multiple authors after only naming one author in the title."
    "If unclear, suggest author as Various and Title as Unknown."
)

def build_user_msg(prompt_text: str) -> str:
    return (
        f"Given the following rawtext from the first 10 pages of a PDF, guess probable author, title, and publication year."
        f"Here are 10 examples of how I want titles to be structured:"
        f"SpringerOpen - African Handbook of Climate Change Adaptation (2022)"
        f"GIZ & NCFA & UNEP-FI & Global Canopy & Emerging Markets Dialogu - making FIs more resilient to environmental risks (Apr, 2017)"
        f"NBER - Adapting To Flood Risk Evidence From A Panel Of Global Cities (2022)"
        f"Gaby Frangieh - Credit spread risk in the banking book (2025)"
        f"Banca d'Italia & IMF - Embedding sustainability in credit risk assessment (Mar, 2025)"
        f"Augusto Blanc-Blocquel etal - Climate-related default probabilities (2024)"
        f"Misereor - Towards a socio-ecological transformation of the economy (Mar, 2024)"
        f"Esther Shears etal - How central banks manage climate and energy transition risks (Feb, 2025)"
        f"OECD & ColumbiaU - Harnessing mission governance to achieve national climate targets (2025)"
        f"OxfordU - Input for the update of the SBTi corporate net-zero standard (April, 2025)"
        f"Put simply, your guess should look like this: OrgA & OrgB & Jane Smith - The Document Title- Subtitles (2023)."
        f"Please output strictly JSON in the following format: {{'author':'', 'title':'', 'pubdate':''}}. "
        f"----\n{prompt_text}\n----"
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
    # Do not replace spaces with underscores; just remove forbidden characters and trim length
    return name[:max_length].strip()

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
