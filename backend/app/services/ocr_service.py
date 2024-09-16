from google.cloud import vision
from google.cloud.vision import types
from app.core.config import get_settings
from app.services.storage_service import get_file_content

def process_document(file_path: str) -> str:
    # Retrieve file content from storage
    file_content = get_file_content(file_path)

    # Initialize Google Cloud Vision client
    settings = get_settings()
    client = vision.ImageAnnotatorClient()

    # Perform OCR on the document
    image = types.Image(content=file_content)
    response = client.document_text_detection(image=image)

    # Extract and concatenate text from OCR result
    extracted_text = ""
    for page in response.full_text_annotation.pages:
        for block in page.blocks:
            for paragraph in block.paragraphs:
                for word in paragraph.words:
                    word_text = ''.join([symbol.text for symbol in word.symbols])
                    extracted_text += word_text + " "

    return extracted_text.strip()

# HUMAN ASSISTANCE NEEDED
# The following aspects may need human review:
# 1. Error handling: Add appropriate error handling for file retrieval and OCR processing.
# 2. Authentication: Ensure proper authentication is set up for Google Cloud Vision API.
# 3. Performance optimization: Consider adding caching or batch processing for large documents.
# 4. Language support: Add support for multiple languages if required.
# 5. Confidence threshold: Implement a confidence threshold for extracted text if needed.