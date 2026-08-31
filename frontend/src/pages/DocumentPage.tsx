import React from 'react';
import { DocumentUpload } from '../components/DocumentUpload';
import type { DocumentResponse, WorkflowStatus } from '../types/api';

interface DocumentPageProps {
  onWorkflowStarted: (workflow: WorkflowStatus, document: DocumentResponse) => void;
}

export const DocumentPage: React.FC<DocumentPageProps> = ({ onWorkflowStarted }) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>
      <DocumentUpload onWorkflowStarted={onWorkflowStarted} />
    </div>
  );
};
