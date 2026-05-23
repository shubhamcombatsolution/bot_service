import fitz  # PyMuPDF
import pdfplumber
import os
import shutil
from PIL import Image
from io import BytesIO
import pandas as pd
import openai
import base64

# Set OpenAI API Key from environment variable
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise RuntimeError("OPENAI_API_KEY environment variable is required")
openai.api_key = openai_api_key

# Directories for classified images
valid_dir = "valid_images"
invalid_dir = "invalid_images"
os.makedirs(valid_dir, exist_ok=True)
os.makedirs(invalid_dir, exist_ok=True)

def extract_text(pdf_path):
    """Extracts text from a PDF using PyMuPDF."""
    try:
        doc = fitz.open(pdf_path)
        text = "\n".join([page.get_text() for page in doc])
        return text
    except Exception as e:
        print(f"Error extracting text: {e}")
        return ""

def extract_metadata(pdf_path):
    """Extracts metadata from a PDF using PyMuPDF."""
    try:
        doc = fitz.open(pdf_path)
        return doc.metadata
    except Exception as e:
        print(f"Error extracting metadata: {e}")
        return {}

def extract_images_from_pdf(pdf_path, output_folder="extracted_images"):
    """Extracts images from a PDF without cropping or resizing and saves them with full details."""
    
    os.makedirs(output_folder, exist_ok=True)
    doc = fitz.open(pdf_path)
    image_paths = []
    
    try:
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            images = page.get_images(full=True)  # Extract all images from the page
            
            for img_index, img in enumerate(images):
                xref = img[0]  # Image reference ID
                base_image = doc.extract_image(xref)  # Extract image data
                
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                # Ensure correct image extension
                if image_ext not in ["jpeg", "png"]:
                    image_ext = "png"

                image = Image.open(BytesIO(image_bytes))
                image_path = os.path.join(output_folder, f"page{page_num+1}_img{img_index+1}.{image_ext}")
                
                image.save(image_path)
                image_paths.append(image_path)
    
    except Exception as e:
        print(f"Error extracting images: {e}")
    
    return image_paths

def classify_image(image_path, prompt):
    """Classifies an image using OpenAI's GPT-4 Turbo Vision model."""
    
    try:
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode("utf-8")

        # Correct OpenAI API call with properly formatted image URL
        response = openai.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "You are an AI that classifies images."},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                ]}
            ],
            max_tokens=100
        )

        classification = response.choices[0].message.content.strip()  # Extract classification result
        return classification

    except Exception as e:
        print(f"Error classifying image {image_path}: {e}")
        return "invalid"

def process_images(pdf_path, prompt):
    """Extracts images from a PDF, classifies them, and moves them to appropriate folders."""
    
    image_paths = extract_images_from_pdf(pdf_path)
    
    for image_path in image_paths:
        classification = classify_image(image_path, prompt)
        
        try:
            if "valid" in classification.lower():  # Adjust condition based on classification output
                shutil.move(image_path, os.path.join(valid_dir, os.path.basename(image_path)))
            else:
                shutil.move(image_path, os.path.join(invalid_dir, os.path.basename(image_path)))
        
        except Exception as e:
            print(f"Error moving image {image_path}: {e}")

def extract_tables(pdf_path):
    """Extracts tables from a PDF using pdfplumber."""
    tables = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                table = page.extract_table()
                if table:
                    df = pd.DataFrame(table[1:], columns=table[0])
                    tables.append(df)
    except Exception as e:
        print(f"Error extracting tables: {e}")
    
    return tables

# Example usage
pdf_file = "sample.pdf"

# Extract text
text = extract_text(pdf_file)
print("Extracted Text:")
print(text[:500])  # Print the first 500 characters

# Extract metadata
metadata = extract_metadata(pdf_file)
print("\nMetadata:")
for key, value in metadata.items():
    print(f"{key}: {value}")

# Extract images and classify them
#classification_prompt = """
#Analyze this image and determine if it is valid or invalid based on the following criteria:
#- Valid: The image contains clearly recognizable objects, readable text, or meaningful visual content that could be used in a presentation or document.
#- Invalid: The image is blank, severely corrupted, contains only noise/artifacts, is completely blurred, or lacks any distinguishable content.
#
#Please classify as either 'valid' or 'invalid' only, no extra text.
#"""

#process_images(pdf_file, classification_prompt)

# Extract tables
tables = extract_tables(pdf_file)
print("\nExtracted Tables:")
for i, table in enumerate(tables):
    print(f"\nTable {i+1}:")
    print(table)
