from imaplib import IMAP4_SSL
from email import message_from_bytes
from email.utils import parseaddr
from app.core.config import get_settings
from app.db.models import EmailMetadata
from app.services.storage_service import upload_attachment
from typing import List, Dict

# HUMAN ASSISTANCE NEEDED
# The following function has a confidence level of 0.7, which is below the threshold of 0.8.
# Additional review and potential modifications may be required for production readiness.

def process_emails(Session) -> List[Dict]:
    settings = get_settings()
    processed_emails = []

    try:
        # Connect to the email server
        with IMAP4_SSL(settings.EMAIL_SERVER) as imap:
            imap.login(settings.EMAIL_USERNAME, settings.EMAIL_PASSWORD)
            imap.select('INBOX')

            # Retrieve unread emails
            _, message_numbers = imap.search(None, 'UNSEEN')
            for num in message_numbers[0].split():
                _, msg_data = imap.fetch(num, '(RFC822)')
                email_body = msg_data[0][1]
                email_message = message_from_bytes(email_body)

                # Parse email content and attachments
                sender_name, sender_email = parseaddr(email_message['From'])
                subject = email_message['Subject']
                date = email_message['Date']

                attachments = []
                for part in email_message.walk():
                    if part.get_content_maintype() == 'multipart':
                        continue
                    if part.get('Content-Disposition') is None:
                        continue
                    
                    filename = part.get_filename()
                    if filename:
                        # Upload attachments to storage
                        file_content = part.get_payload(decode=True)
                        storage_path = upload_attachment(filename, file_content)
                        attachments.append({"filename": filename, "storage_path": storage_path})

                # Create EmailMetadata record
                with Session() as session:
                    email_metadata = EmailMetadata(
                        sender_name=sender_name,
                        sender_email=sender_email,
                        subject=subject,
                        received_date=date,
                        attachments=attachments
                    )
                    session.add(email_metadata)
                    session.commit()

                # Mark email as processed
                imap.store(num, '+FLAGS', '\\Seen')

                processed_emails.append({
                    "id": email_metadata.id,
                    "sender_email": sender_email,
                    "subject": subject,
                    "received_date": date,
                    "attachments": attachments
                })

    except Exception as e:
        # Log the error and potentially raise it for higher-level handling
        print(f"Error processing emails: {str(e)}")
        # Consider adding more robust error handling and logging here

    return processed_emails