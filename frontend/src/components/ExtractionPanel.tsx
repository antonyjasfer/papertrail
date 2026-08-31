import React from 'react';
import type { WorkflowStatus } from '../types/api';
import { StatusBadge } from './StatusBadge';

interface ExtractionPanelProps {
  workflow: WorkflowStatus | null;
}

export const ExtractionPanel: React.FC<ExtractionPanelProps> = ({ workflow }) => {
  if (!workflow) {
    return (
      <div className="card">
        <div className="card-header">
          <h3>Extracted Evidence</h3>
        </div>
        <div className="card-body">
          <div className="empty-state">
            <p>No document currently selected for extraction view.</p>
          </div>
        </div>
      </div>
    );
  }

  const isExtracted = [
    'EXTRACTED',
    'FORENSIC_ANALYSIS',
    'COMPLIANCE_ANALYSIS',
    'RISK_ASSESSED',
    'AUDIT_SEALED',
    'REPORT_GENERATED',
    'COMPLETED',
    'REQUIRES_REVIEW',
  ].includes(workflow.current_state);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>
      <div className="card">
        <div className="card-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <h3>Gemini Multimodal Document Extraction</h3>
            <span className="badge badge-info" style={{ textTransform: 'none' }}>
              Gemini 3.5+ · Google GenAI SDK
            </span>
          </div>
          <StatusBadge
            status={isExtracted ? 'COMPLETED' : workflow.current_state === 'EXTRACTING' ? 'RUNNING' : 'PENDING'}
            type="state"
          />
        </div>

        <div className="card-body">
          <div className="info-notice section-gap">
            <span className="notice-icon">ℹ</span>
            <div>
              <strong>Zero-Fabrication Architecture:</strong> PaperTrail uses Gemini 3.5 for multimodal structured entity extraction into a validated Pydantic schema. If upstream errors occur, the system sets status to <code>UPSTREAM_FAILURE</code> without manufacturing synthetic financial records.
            </div>
          </div>

          <div className="detail-grid">
            <div className="detail-item">
              <span className="detail-label">Extraction Pipeline Status</span>
              <span className="detail-value">
                {isExtracted ? 'Extraction Completed & Validated' : workflow.current_state === 'EXTRACTING' ? 'Extracting via Gemini 3.5...' : 'Awaiting Ingestion'}
              </span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Model Target</span>
              <span className="detail-value mono">gemini-3.5-flash / gemini-3.6-flash</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Target Workflow</span>
              <span className="detail-value mono">{workflow.workflow_id}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Document Reference</span>
              <span className="detail-value mono">{workflow.document_id}</span>
            </div>
          </div>

          <div
            style={{
              marginTop: 'var(--space-lg)',
              padding: 'var(--space-md)',
              background: 'var(--color-bg-card-alt)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--color-border)',
              fontSize: '0.82rem',
              color: 'var(--color-text-secondary)',
            }}
          >
            <div style={{ fontWeight: 600, color: 'var(--color-text-primary)', marginBottom: '4px' }}>
              Encapsulated Evidence Payload
            </div>
            Detailed extraction payloads (invoice numbers, vendor/customer entities, line items, and Decimal-quantized totals) are committed to persistent workflow execution claims in Cosmos DB / Firestore and evaluated by downstream forensic rules.
          </div>
        </div>
      </div>
    </div>
  );
};
