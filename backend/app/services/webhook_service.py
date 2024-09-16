import requests
from app.db.models import Webhook
from app.core.config import get_settings
import logging

# HUMAN ASSISTANCE NEEDED
# The following code may need additional error handling and optimization for production use.
# Please review and enhance as necessary.

def send_webhook_notification(application_id: str, status: str, db_session: Session) -> bool:
    settings = get_settings()
    logger = logging.getLogger(__name__)
    
    # Retrieve registered webhooks from database
    webhooks = db_session.query(Webhook).all()
    
    if not webhooks:
        logger.info(f"No registered webhooks found for application {application_id}")
        return True
    
    # Prepare webhook payload
    payload = {
        "application_id": application_id,
        "status": status,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    success = True
    
    # Send POST request to each registered webhook URL
    for webhook in webhooks:
        try:
            response = requests.post(
                webhook.url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=settings.WEBHOOK_TIMEOUT
            )
            response.raise_for_status()
            logger.info(f"Webhook notification sent successfully to {webhook.url}")
        except requests.RequestException as e:
            logger.error(f"Failed to send webhook notification to {webhook.url}: {str(e)}")
            success = False
    
    # Log webhook notification results
    if success:
        logger.info(f"All webhook notifications sent successfully for application {application_id}")
    else:
        logger.warning(f"Some webhook notifications failed for application {application_id}")
    
    # Return overall success status
    return success