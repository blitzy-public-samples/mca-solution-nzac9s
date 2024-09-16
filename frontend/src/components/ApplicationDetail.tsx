import React, { useState, useEffect } from 'react';
import { getApplicationById } from '@/services/api';
import { DocumentViewer } from '@/components/DocumentViewer';
import { formatDate, formatCurrency, formatPhoneNumber } from '@/utils/formatters';

interface Application {
  id: string;
  merchantName: string;
  ownerName: string;
  phoneNumber: string;
  email: string;
  fundingAmount: number;
  fundingTerm: number;
  submissionDate: string;
  attachments: string[];
  emailMetadata: {
    sender: string;
    recipient: string;
    subject: string;
    timestamp: string;
  };
}

// HUMAN ASSISTANCE NEEDED
// The following component needs review and potential improvements for production readiness.
// Areas that may need attention:
// - Error handling for API calls
// - Loading state management
// - Input validation for editable fields
// - Accessibility improvements
// - Responsive design considerations
// - Performance optimizations for large datasets

const ApplicationDetail: React.FC<{ applicationId: string }> = ({ applicationId }) => {
  const [application, setApplication] = useState<Application | null>(null);
  const [isEditing, setIsEditing] = useState(false);

  useEffect(() => {
    const fetchApplication = async () => {
      try {
        const data = await getApplicationById(applicationId);
        setApplication(data);
      } catch (error) {
        console.error('Error fetching application:', error);
        // TODO: Implement proper error handling
      }
    };

    fetchApplication();
  }, [applicationId]);

  if (!application) {
    return <div>Loading...</div>;
  }

  const handleEdit = () => {
    setIsEditing(true);
  };

  const handleSave = () => {
    // TODO: Implement save functionality
    setIsEditing(false);
  };

  return (
    <div className="application-detail">
      <h1>Application Details</h1>
      
      <section className="merchant-info">
        <h2>Merchant Information</h2>
        <p>Name: {isEditing ? <input value={application.merchantName} /> : application.merchantName}</p>
        <p>Phone: {isEditing ? <input value={application.phoneNumber} /> : formatPhoneNumber(application.phoneNumber)}</p>
        <p>Email: {isEditing ? <input value={application.email} /> : application.email}</p>
      </section>

      <section className="owner-info">
        <h2>Owner Information</h2>
        <p>Name: {isEditing ? <input value={application.ownerName} /> : application.ownerName}</p>
      </section>

      <section className="funding-details">
        <h2>Funding Details</h2>
        <p>Amount: {formatCurrency(application.fundingAmount)}</p>
        <p>Term: {application.fundingTerm} months</p>
        <p>Submission Date: {formatDate(application.submissionDate)}</p>
      </section>

      <section className="attachments">
        <h2>Attachments</h2>
        {application.attachments.map((attachment, index) => (
          <DocumentViewer key={index} documentUrl={attachment} />
        ))}
      </section>

      <section className="email-metadata">
        <h2>Email Metadata</h2>
        <p>Sender: {application.emailMetadata.sender}</p>
        <p>Recipient: {application.emailMetadata.recipient}</p>
        <p>Subject: {application.emailMetadata.subject}</p>
        <p>Timestamp: {formatDate(application.emailMetadata.timestamp)}</p>
      </section>

      {isEditing ? (
        <button onClick={handleSave}>Save</button>
      ) : (
        <button onClick={handleEdit}>Edit</button>
      )}
    </div>
  );
};

export default ApplicationDetail;