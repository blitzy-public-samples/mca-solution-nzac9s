from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.schema.application_schema import Attachment
from app.services.storage_service import upload_file

router = APIRouter()

@router.post('/applications/{application_id}/attachments/', response_model=Attachment)
async def upload_attachment(application_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    # HUMAN ASSISTANCE NEEDED
    # This function needs additional error handling and validation
    # Validate application exists
    # TODO: Implement application validation

    # Upload file to storage
    file_url = await upload_file(file)

    # Create attachment record in database
    new_attachment = Attachment(
        application_id=application_id,
        file_name=file.filename,
        file_url=file_url
    )
    db.add(new_attachment)
    db.commit()
    db.refresh(new_attachment)

    # Return created attachment
    return new_attachment

@router.get('/attachments/{attachment_id}', response_model=Attachment)
def get_attachment(attachment_id: str, db: Session = Depends(get_db)):
    # Query database for attachment
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()

    # Raise 404 if not found
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")

    # Return attachment
    return attachment