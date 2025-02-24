##############
# Name: openai-pdf-renamer
# Author: Naveen Srivatsav
# Version: 0.5
# Description: This script takes a folder full of badly-named PDFs, 
# extracts text from the first page, sends that text to OpenAI
# gets response in JSON format with title author and pubdate
# and renames the files accordingly
# this version also updates the metadata for the file
#############


import os
import re
import time
import json
from openai import OpenAI
from PyPDF2 import PdfReader, PdfWriter
from datetime import datetime

# --- CONFIGURATION ---

# Replace with your actual API key.  Keep this secret!
chai = OpenAI(api_key="INSERT_API_KEY_HERE")

# --- HELPER FUNCTIONS ---


def extract_text_from_pdf(pdf_path):
    """
    Extracts text from the first page of a PDF.  No OCR.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Extracted text as a string, or None if extraction fails.
    """
    try:
        reader = PdfReader(pdf_path)
        page = reader.pages[0]
        text = page.extract_text()
        return text
    except Exception as e:
        print(f"Error during text extraction: {e}")
        return None


def llm_guess(rip_text):
    """
    Sends text to OpenAI to get title, author, and publication date.
    """
    try:
        response = chai.chat.completions.create(
            model="gpt-3.5-turbo",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a librarian interested in the organization of knowledge. "
                        "You will assist the user in renaming digital files to build a perfect library of documents. "
                        "You will only respond in JSON output, strictly with author, title and pubdate values as strings. "
                        "All strings should follow Camel Capitalisation rules."
                    ),
                },
                {
                    "role": "user",
                    "content": f"""Given the following text, what are the most likely values for title and author?
                        I want to copy-paste your response directly as a filename that maximizes discoverability.
                        I need to know the author starting with notable institutional acronyms then a human-readable title string
                        that can be googled to rediscover the original document and finally the year of publication in parentheses.
                        Here's a couple of EXAMPLE filenames that your responses should match.
                        EXAMPLE 1: A4S & Neil Gaiman & etal - A4S Essential Guide to Incentivizing Action Along the Value Chain (2022)
                        EXAMPLE 2: CFRF & Harry Styles - Case studies on climate action (2021)
                        EXAMPLE 3: IPCC & UNEP-FI & etal - AR6 WGII Climate Change 2022 - Annex I Global to regional atlas (2022)

                        Provide your response strictly in JSON with the following logical-syntax following Camel Capitalisation rules with no other accompanying text.
                        author: First_Priority_would_be_the_Institutional_Acronym OR First_Author_FirstName And_LastName AND_ONLY_IF_UNABLE_TO_GUESS_PRINT_Various
                        title: Title and Subtitle of Report without any special symbols ONLY_IF_UNABLE_TO_GUESS_PRINT_Unknown
                        pubdate: YYYY_first_published_digits_only

                        --------------
                        The text to be processed is
                        ----------
                        \"{rip_text}\"
                        """,
                },
            ],
        )

        output_text = response.choices[0].message.content.strip()
        return output_text
    except Exception as e:
        print(f"Error from OpenAI API: {e}")
        return None


def validate_and_trim_filename(initial_filename):
    """
    Validates and trims a filename, removing special characters and limiting length.
    """
    # Allow letters, numbers, underscores, hyphens, spaces, parentheses, and ampersands.
    cleaned_filename = re.sub(r"[^\w\s\(\)\-\&]", "", initial_filename)
    return cleaned_filename[:200]  # Limit to 200 characters


def rename_pdf_based_on_title(pdf_path):
    """
    Analyzes a PDF, suggests a new name, and renames/updates metadata.
    Preserves original name if AI suggestion is unreliable.

    Args:
        pdf_path: The full path to the PDF file.

    Returns:
        new_file_path: The full path to the renamed file (or original if unchanged), or None on error.
    """
    original_filename = os.path.basename(pdf_path)  # Store original filename

    rip_text = extract_text_from_pdf(pdf_path)
    if rip_text is None:
        print(f"Skipping {original_filename} due to text extraction failure.")
        return None

    llm_guessed_response = llm_guess(rip_text)
    if llm_guessed_response is None:
        print(f"Skipping {original_filename} due to OpenAI API failure.")
        return None  # Don't rename if API call fails

    try:
        guessed_json = json.loads(llm_guessed_response)
        # Check for "UNKNOWN" or "Various" in title or author
        if (
            guessed_json["title"].upper() == "UNKNOWN"
            or guessed_json["author"].upper() == "VARIOUS"
            or guessed_json["author"].upper() == "UNKNOWN"
        ):
            print(
                f"AI suggestion unreliable. Keeping original name: {original_filename}"
            )
            return pdf_path  # Return original path

        guessed_name = (
            f"{guessed_json['author']} - {guessed_json['title']} ({str(guessed_json['pubdate'])})"
        )
        clean_name = validate_and_trim_filename(guessed_name)
        clean_author = validate_and_trim_filename(guessed_json["author"])
        clean_title = validate_and_trim_filename(guessed_json["title"])
        clean_date = guessed_json["pubdate"]  # Keep it simple

        # Ensure the .pdf extension
        if not clean_name.lower().endswith(".pdf"):
            clean_name += ".pdf"

        new_file_path = os.path.join(os.path.dirname(pdf_path), clean_name)

        # Handle potential duplicate filenames
        counter = 1
        while os.path.exists(new_file_path):
            base, ext = os.path.splitext(clean_name)
            new_file_path = os.path.join(
                os.path.dirname(pdf_path), f"{base}_{counter}{ext}"
            )
            counter += 1

        # Rewrite metadata *before* renaming
        try:
            reader = PdfReader(pdf_path)
            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)

            metadata = {
                "/Title": clean_title,
                "/Author": clean_author,
                "/CreationDate": clean_date,  # Consider using a proper date format here if needed
            }
            writer.add_metadata(metadata)

            # Write to a *temporary* file first
            temp_pdf_path = pdf_path + ".temp"
            with open(temp_pdf_path, "wb") as f:
                writer.write(f)

            # Rename the original file (acting as a backup)
            os.rename(pdf_path, pdf_path + ".bak")

            # Rename the temp file to the target
            os.rename(temp_pdf_path, new_file_path)

            # Now, remove the backup file
            os.remove(pdf_path + ".bak")

        except Exception as e:
            print(f"Error updating metadata or writing file: {e}")
            return pdf_path  # Return the original path

        print(f"Renamed '{original_filename}' to '{os.path.basename(new_file_path)}'")
        return new_file_path

    except (json.JSONDecodeError, KeyError) as e:
        print(
            f"Error processing AI response: {e}.  Keeping original name: {original_filename}"
        )
        return pdf_path  # Return original path on parsing error


def rename_pdfs_in_directory(directory):
    """
    Processes all PDFs in a directory.
    """
    pdf_files = [f for f in os.listdir(directory) if f.lower().endswith(".pdf")]
    pdf_files.sort(
        key=lambda x: os.path.getmtime(os.path.join(directory, x)), reverse=True
    )

    for filename in pdf_files:
        filepath = os.path.join(directory, filename)
        rename_pdf_based_on_title(filepath)

    print("Finished processing!")


def main():
    directory = ""  # Can hardcode a directory here for testing
    if not directory:
        directory = input("Please enter the directory containing the PDFs: ")
        if not os.path.isdir(directory):
            print("Invalid directory. Exiting.")
            return

    rename_pdfs_in_directory(directory)


if __name__ == "__main__":
    main()
