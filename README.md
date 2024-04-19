# openai-pdf-renamer
This script takes a folder full of badly-named PDFs, extracts text from the first page, sends that text to OpenAI and renames files with the results.

v0.1 - direct filename dump from OpenAI response
v0.2 - OpenAI response structured as JSON with title, author and pubdate fields (coming soon)
v0.3 - PDF metadata is also replaced with guessed content (coming soon)
