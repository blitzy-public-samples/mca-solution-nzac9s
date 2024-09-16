from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.db.database import get_db
from app.schema.application_schema import Application, ApplicationCreate
from app.services.data_extraction import extract_application_data
from app.services.ocr_service import process_document

router = APIRouter()

@router.post('/applications/', response_model=Application)
def create_application(application: ApplicationCreate, db: Session = Depends(get_db)):
    # HUMAN ASSISTANCE NEEDED
    # This function has a confidence level of 0.7 and may need review for production readiness
    # Implement additional error handling and input validation as needed
    
    # Validate input data
    # TODO: Add more comprehensive input validation

    # Process attached documents using OCR
    ocr_results = process_document(application.document)

    # Extract application data
    extracted_data = extract_application_data(ocr_results)

    # Create application in database
    db_application = Application(**application.dict(), **extracted_data)
    db.add(db_application)
    db.commit()
    db.refresh(db_application)

    # Return created application
    return db_application

@router.get('/applications/{application_id}', response_model=Application)
def get_application(application_id: int, db: Session = Depends(get_db)):
    # Query database for application
    application = db.query(Application).filter(Application.id == application_id).first()
    
    # Raise 404 if not found
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    
    # Return application
    return application

@router.get('/applications/', response_model=List[Application])
def list_applications(db: Session = Depends(get_db)):
    # Query database for all applications
    applications = db.query(Application).all()
    
    # Return list of applications
    return applications