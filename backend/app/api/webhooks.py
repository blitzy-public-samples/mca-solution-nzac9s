from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.db.database import get_db
from app.schema.application_schema import Webhook, WebhookCreate
from app.services.webhook_service import register_webhook, trigger_webhook

router = APIRouter()

@router.post('/webhooks/', response_model=Webhook)
def create_webhook(webhook: WebhookCreate, db: Session = Depends(get_db)):
    # HUMAN ASSISTANCE NEEDED
    # This function needs additional error handling and input validation
    try:
        # Validate input data
        # TODO: Add more specific validation logic here

        # Register webhook with service
        registered_webhook = register_webhook(webhook)

        # Create webhook record in database
        db_webhook = Webhook(**registered_webhook.dict())
        db.add(db_webhook)
        db.commit()
        db.refresh(db_webhook)

        # Return created webhook
        return db_webhook
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create webhook: {str(e)}")

@router.get('/webhooks/', response_model=List[Webhook])
def get_webhooks(db: Session = Depends(get_db)):
    # Query database for all webhooks
    webhooks = db.query(Webhook).all()

    # Return list of webhooks
    return webhooks

@router.delete('/webhooks/{webhook_id}')
def delete_webhook(webhook_id: str, db: Session = Depends(get_db)):
    # Query database for webhook
    webhook = db.query(Webhook).filter(Webhook.id == webhook_id).first()

    # Raise 404 if not found
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    # Delete webhook from database
    db.delete(webhook)
    db.commit()

    # Return confirmation message
    return {"message": f"Webhook {webhook_id} has been deleted"}