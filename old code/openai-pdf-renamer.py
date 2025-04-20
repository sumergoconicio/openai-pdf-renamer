##############
# Name: openai-pdf-renamer
# Author: Naveen Srivatsav
# Version: 0.1
# Description: This script takes a folder full of badly-named PDFs, 
# extracts text from the first page, sends that text to OpenAI and renames files with the results.
#############


# libraries
import os, re, time
from openai import OpenAI
from PyPDF2 import PdfReader
from datetime import datetime

# I like to call my AIs ChAI (Chat+AI) for short.
chai = OpenAI(api_key=INSERT_YOUR_OPENAI_API_KEY_HERE)

# this function reads the 1st page of a PDF, and returns a guessed string of authors and title based on GPT-4-Turbo suggestions
def rename_pdf_based_on_title(pdf_path):
    # Ensure the PDF file exists
    if not os.path.exists(pdf_path):
        print(f"File {pdf_path} does not exist.")
        return None

    # Open the PDF and read its first page
    reader = PdfReader(pdf_path)
    metadata = reader.metadata
    page = reader.pages[0]
    rip_text = page.extract_text()

	 #sending text to OpenAI
    guessed_name=llm_guess(rip_text)
	 
	 #removing special symbols from response and truncating to 200 characters
    clean_name=validate_and_trim_filename(guessed_name)
    #print(rip_text)
    #print(guessed_name)
    #print(clean_name)

    return clean_name

# this function sends the first page extract to OpenAI and gives specific instructions on how to format the results (good enough for me) but you can easily change the instructions here. GPT-4-Turbo might be overkill but cheap enough for me.
def llm_guess(rip_text):
    try:
        response = chai.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "You are a librarian interested in the organisation of knowledge. You will assist the user in renaming digital files to build a perfect library of documents."},
                {"role": "user", "content": f"Given the following text, what are the most likely values for title and author? I want to copy-paste your response directly as a filename that maximises discoverability. I need to know the author starting with notable institutional acronyms then a human-readable title string that can be googled to rediscover the original document and finally the year of publication in parentheses. Provide your response strictly with the following syntax following Title Capitalisation rules with no other accompanying text: ONEINSTITUTIONONLYIFAPPLICABLE OR FIRSTAUTHORONLY_FIRSTNAME LASTNAMENOCOMMAS & ETALFORALLOTHERAUTHORS -dash- TITLE SUBTITLE OF DOCUMENT NOSPECIALSYMBOLS (YYYY). The text to be processed is \n----------\n\"{rip_text}\""}
            ]
        )
        
        output_text = response.choices[0].message.content.strip()
        #print(output_text)
        return output_text
    except Exception as e:
        print({e})
        return None
        

# this function removes special characters and truncates potential filenames to 200 characters    
def validate_and_trim_filename(initial_filename):
    allowed_chars = r'[a-zA-Z0-9_]'
    
    if not initial_filename:
        timestamp = time.strftime('%Y%m%d%H%M%S', time.gmtime())
        return f'empty_file_{timestamp}'
    
    if re.match("^[A-Za-z0-9_]$", initial_filename):
        return initial_filename if len(initial_filename) <= 200 else initial_filename[:200]
    else:
        cleaned_filename = re.sub("^[A-Za-z0-9_]$", '', initial_filename)
        return cleaned_filename if len(cleaned_filename) <= 200 else cleaned_filename[:200]
        

# this is the primary function that detects PDFs in a directory, asks for a new filename and then renames each file accordingly, making sure to add a EXTENSION as suffix.        
def rename_pdfs_in_directory(directory):
    pdf_contents = []
    files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
    files.sort(key=lambda x: os.path.getmtime(os.path.join(directory, x)), reverse=True)
    for filename in files:
        if filename.endswith(".pdf"):
            filepath = os.path.join(directory, filename)
            print(f"Found file {filepath}")
            
            new_file_name = rename_pdf_based_on_title(filepath)
            if not new_file_name.endswith(".pdf"):
                new_file_name = new_file_name + ".pdf"
            else:
                print("already a PDF")
            
            if new_file_name in [f for f in os.listdir(directory) if f.endswith(".pdf")]:
                print(f"The new filename '{new_file_name}' already exists.")
                new_file_name += "_01"

            if new_file_name != None:    
                new_filepath =os.path.join(directory, new_file_name)
            try:
                os.rename(filepath, new_filepath)
                print(f"File renamed to {new_filepath}")
            except Exception as e:
                print(f"An error occurred while renaming the file: {e}")


# this is the MAIN function; you can input a dedicated folder-path to process when you run the script or it will ask you to input the path otherwise
def main():
    directory = ''  # Replace with your PDF directory path
    if directory == '':
      directory = input("Please input your path:")
    rename_pdfs_in_directory(directory)


if __name__ == "__main__":
    main()
