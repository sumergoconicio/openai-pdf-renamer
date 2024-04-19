# openai-pdf-renamer
This script does the following:
- takes a folder full of badly-named PDFs,
- extracts text from the first page,
- sends that text to OpenAI to guess the title, author and date of first publication
- and renames files with the results.

**Caution**

Please manage the security of your own data. 
Any loss of personal content due to errors in this script are your responsibility. Vet, test and modify the script to meet your needs.

**Known issues**
This script will not work on OCR image-based PDFs. The process will return Unknown - Unknown values for metadata, and documents will get rewritten. Don't do it.

**Changelog**
- v0.1 - direct filename dump from OpenAI response
- v0.2 - OpenAI response structured as JSON with title, author and pubdate fields
- v0.3 - PDF metadata is also replaced with guessed content (coming soon)
