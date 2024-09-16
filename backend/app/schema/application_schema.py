from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class Merchant(BaseModel):
    business_legal_name: str
    dba_name: str
    federal_tax_id: str
    address: str
    industry: str
    annual_revenue: float

class Owner(BaseModel):
    name: str
    ssn: str
    address: str
    date_of_birth: datetime
    ownership_percentage: float

class FundingDetails(BaseModel):
    amount_requested: float
    use_of_funds: str

class Attachment(BaseModel):
    type: str
    storage_url: str
    upload_date: datetime

class EmailMetadata(BaseModel):
    sender: str
    subject: str
    body: str
    received_at: datetime

class Application(BaseModel):
    merchant: Merchant
    owners: List[Owner]
    funding_details: FundingDetails
    attachments: List[Attachment]
    email_metadata: EmailMetadata
    status: str
    submission_date: datetime
    processed_date: Optional[datetime]

# HUMAN ASSISTANCE NEEDED
# Please review the Application class to ensure all fields are correctly defined and no additional fields are required for a complete MCA application.