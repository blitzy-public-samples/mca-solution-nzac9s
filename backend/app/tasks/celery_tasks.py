from celery import Celery
from app.core.config import get_settings
from app.services.email_processor import process_emails
from app.services.ocr_service import process_document
from app.services.data_extraction import extract_application_data
from app.services.webhook_service import send_webhook_notification
from app.db.database import SessionLocal

celery_app = Celery('mca_processor', broker=get_settings().CELERY_BROKER_URL)

@celery_app.task
def process_incoming_emails():
    db = SessionLocal()
    try:
        status = process_emails()
        db.commit()
        return status
    finally:
        db.close()

@celery_app.task
def ocr_document(file_path: str):
    # HUMAN ASSISTANCE NEEDED
    # This function has a confidence level of 0.7, which is below the threshold.
    # Please review and improve the implementation if necessary.
    extracted_text = process_document(file_path)
    return extracted_text

@celery_app.task
def extract_application_data_task(ocr_text: str, application_id: str):
    # HUMAN ASSISTANCE NEEDED
    # This function has a confidence level of 0.6, which is below the threshold.
    # Please review and improve the implementation, especially regarding error handling and data validation.
    db = SessionLocal()
    try:
        extracted_data = extract_application_data(ocr_text)
        
        # Update application status in database
        # Note: Implement the actual database update logic here
        
        db.commit()
        
        # Trigger webhook notification
        send_webhook_notification(application_id, extracted_data)
        
        return extracted_data
    except Exception as e:
        db.rollback()
        # Log the error and handle it appropriately
        raise
    finally:
        db.close()