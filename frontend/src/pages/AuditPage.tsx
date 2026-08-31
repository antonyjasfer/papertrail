import React from 'react';
import { AuditPanel } from '../components/AuditPanel';
import type { WorkflowStatus } from '../types/api';

interface AuditPageProps {
  workflow: WorkflowStatus | null;
}

export const AuditPage: React.FC<AuditPageProps> = ({ workflow }) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>
      <AuditPanel workflow={workflow} />
    </div>
  );
};
