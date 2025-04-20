# openai-pdf-renamer
This script helps you organize and rename PDFs using the OpenAI API. It:
- Prompts you for a directory containing PDFs
- Extracts text from the first 5 pages of each PDF
- Sends the extracted text to OpenAI to guess the title, author, and publication year
- Skips renaming if the AI response is unreliable (e.g., "Unknown" or "Various")
- Renames the file using the format: `Author - Title (Year).pdf`
- Updates PDF metadata (Title, Author, CreationDate) with the guessed values

**Caution**

Please manage the security of your own data. 
Any loss of personal content due to errors in this script are your responsibility. Vet, test and modify the script to meet your needs.
I personally find that Claude Haiku manages better and more reliable outputs than GPT-4.1-mini.

**Requirements**
- Python 3.8+
- See `requirements.txt` for dependencies

**Installation**
```bash
pip install -r requirements.txt
```

**Usage**
1. Set your OpenAI API key as an environment variable:
   ```bash
   export OPENAI_API_KEY=sk-...
   ```
2. Run the script:
   ```bash
   python openai_pdf_renamer.py
   ```
   You will be prompted to enter the directory containing your PDF files.

**Notes**
- The script skips files if the AI cannot reliably guess the author or title.
- It will not work on image-based (non-text) PDFs.
- Always keep backups of your data before running batch renaming scripts.

**Changelog**
- v0.1 - direct filename dump from OpenAI response
- v0.2 - OpenAI response structured as JSON with title, author and pubdate fields
- v0.3 - PDF metadata is also replaced with guessed content
- v0.5 - affordances for "unknown" results defaults to preserving original filenames
- v1.0 - prompts for directory, extracts from first 5 pages, skips unreliable AI, updates metadata, and requires OpenAI API key
