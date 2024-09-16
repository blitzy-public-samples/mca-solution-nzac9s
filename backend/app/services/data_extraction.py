import re
from app.schema.application_schema import Application, Merchant, Owner, FundingDetails
from app.services.ocr_service import process_document

def extract_application_data(ocr_text: str) -> Application:
    # HUMAN ASSISTANCE NEEDED
    # The following code is a basic implementation and may need refinement for production use.
    # Regular expressions and data extraction logic should be reviewed and improved.

    # Define regular expressions for data extraction
    merchant_regex = r"Business Name:\s*(.*?)\nAddress:\s*(.*?)\nPhone:\s*(.*?)\n"
    owner_regex = r"Owner Name:\s*(.*?)\nSSN:\s*(.*?)\nDOB:\s*(.*?)\n"
    funding_regex = r"Requested Amount:\s*\$?([\d,]+)\nPurpose:\s*(.*?)\n"

    # Extract merchant information
    merchant_match = re.search(merchant_regex, ocr_text, re.DOTALL)
    if merchant_match:
        merchant = Merchant(
            business_name=merchant_match.group(1).strip(),
            address=merchant_match.group(2).strip(),
            phone=merchant_match.group(3).strip()
        )
    else:
        merchant = Merchant(business_name="", address="", phone="")

    # Extract owner information
    owner_match = re.search(owner_regex, ocr_text, re.DOTALL)
    if owner_match:
        owner = Owner(
            name=owner_match.group(1).strip(),
            ssn=owner_match.group(2).strip(),
            dob=owner_match.group(3).strip()
        )
    else:
        owner = Owner(name="", ssn="", dob="")

    # Extract funding details
    funding_match = re.search(funding_regex, ocr_text, re.DOTALL)
    if funding_match:
        funding_details = FundingDetails(
            requested_amount=float(funding_match.group(1).replace(',', '')),
            purpose=funding_match.group(2).strip()
        )
    else:
        funding_details = FundingDetails(requested_amount=0.0, purpose="")

    # Create and return Application object with extracted data
    return Application(
        merchant=merchant,
        owner=owner,
        funding_details=funding_details
    )