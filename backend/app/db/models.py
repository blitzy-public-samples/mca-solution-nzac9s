from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from uuid import uuid4

Base = declarative_base()

class Merchant(Base):
    __tablename__ = 'merchants'

    id = Column(UUID, primary_key=True, default=uuid4)
    business_legal_name = Column(String, nullable=False)
    dba_name = Column(String)
    federal_tax_id = Column(String, nullable=False)
    address = Column(String, nullable=False)
    industry = Column(String, nullable=False)
    annual_revenue = Column(Float, nullable=False)

class Owner(Base):
    __tablename__ = 'owners'

    id = Column(UUID, primary_key=True, default=uuid4)
    application_id = Column(UUID, ForeignKey('applications.id'), nullable=False)
    name = Column(String, nullable=False)
    ssn = Column(String, nullable=False)
    address = Column(String, nullable=False)
    date_of_birth = Column(Date, nullable=False)
    ownership_percentage = Column(Float, nullable=False)

class Application(Base):
    __tablename__ = 'applications'

    id = Column(UUID, primary_key=True, default=uuid4)
    merchant_id = Column(UUID, ForeignKey('merchants.id'), nullable=False)
    status = Column(String, nullable=False)
    submission_date = Column(Date, nullable=False)
    processed_date = Column(Date)

    merchant = relationship("Merchant", back_populates="applications")
    owners = relationship("Owner", back_populates="application")
    attachments = relationship("Attachment", back_populates="application")
    email_metadata = relationship("EmailMetadata", back_populates="application")

class Attachment(Base):
    __tablename__ = 'attachments'

    id = Column(UUID, primary_key=True, default=uuid4)
    application_id = Column(UUID, ForeignKey('applications.id'), nullable=False)
    type = Column(String, nullable=False)
    storage_url = Column(String, nullable=False)
    upload_date = Column(Date, nullable=False)

    application = relationship("Application", back_populates="attachments")

class EmailMetadata(Base):
    __tablename__ = 'email_metadata'

    id = Column(UUID, primary_key=True, default=uuid4)
    application_id = Column(UUID, ForeignKey('applications.id'), nullable=False)
    sender = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body = Column(String, nullable=False)
    received_at = Column(Date, nullable=False)

    application = relationship("Application", back_populates="email_metadata")