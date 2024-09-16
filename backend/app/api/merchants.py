from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.schema.application_schema import Merchant, MerchantCreate

router = APIRouter()

@router.post('/merchants/', response_model=Merchant)
def create_merchant(merchant: MerchantCreate, db: Session = Depends(get_db)):
    # Validate input data
    # TODO: Add any additional validation if required

    # Create merchant in database
    db_merchant = Merchant(**merchant.dict())
    db.add(db_merchant)
    db.commit()
    db.refresh(db_merchant)

    # Return created merchant
    return db_merchant

@router.get('/merchants/{merchant_id}', response_model=Merchant)
def get_merchant(merchant_id: str, db: Session = Depends(get_db)):
    # Query database for merchant
    db_merchant = db.query(Merchant).filter(Merchant.id == merchant_id).first()

    # Raise 404 if not found
    if db_merchant is None:
        raise HTTPException(status_code=404, detail="Merchant not found")

    # Return merchant
    return db_merchant