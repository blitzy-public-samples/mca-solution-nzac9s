import React, { useState } from 'react';
import { Document, Page } from 'react-pdf';
import { formatFileSize } from '@/utils/formatters';

// HUMAN ASSISTANCE NEEDED
// The confidence level for this component is below 0.8. 
// Additional review and potential modifications may be required for production readiness.

interface DocumentViewerProps {
  documentUrl: string;
}

const DocumentViewer: React.FC<DocumentViewerProps> = ({ documentUrl }) => {
  const [numPages, setNumPages] = useState<number | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [scale, setScale] = useState(1);
  const [error, setError] = useState<string | null>(null);

  function onDocumentLoadSuccess({ numPages }: { numPages: number }) {
    setNumPages(numPages);
    setError(null);
  }

  function onDocumentLoadError(error: Error) {
    setError(`Error loading document: ${error.message}`);
  }

  function changePage(offset: number) {
    setPageNumber(prevPageNumber => Math.min(Math.max(1, prevPageNumber + offset), numPages || 1));
  }

  function zoomIn() {
    setScale(prevScale => Math.min(prevScale + 0.2, 3));
  }

  function zoomOut() {
    setScale(prevScale => Math.max(prevScale - 0.2, 0.5));
  }

  return (
    <div className="document-viewer">
      {error ? (
        <div className="error-message">{error}</div>
      ) : (
        <>
          <div className="controls">
            <button onClick={() => changePage(-1)} disabled={pageNumber <= 1}>
              Previous
            </button>
            <span>
              Page {pageNumber} of {numPages}
            </span>
            <button onClick={() => changePage(1)} disabled={pageNumber >= (numPages || 1)}>
              Next
            </button>
            <button onClick={zoomIn}>Zoom In</button>
            <button onClick={zoomOut}>Zoom Out</button>
          </div>
          <Document
            file={documentUrl}
            onLoadSuccess={onDocumentLoadSuccess}
            onLoadError={onDocumentLoadError}
            loading={<div>Loading document...</div>}
          >
            <Page
              pageNumber={pageNumber}
              scale={scale}
              renderTextLayer={false}
              renderAnnotationLayer={false}
            />
          </Document>
        </>
      )}
    </div>
  );
};

export default DocumentViewer;