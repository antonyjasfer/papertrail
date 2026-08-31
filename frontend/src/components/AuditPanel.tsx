import React from 'react';
import type { WorkflowStatus } from '../types/api';
import { StatusBadge } from './StatusBadge';

interface AuditPanelProps {
  workflow: WorkflowStatus | null;
}

const AUDIT_EVENT_TYPES = [
  { event: 'DOCUMENT_UPLOADED', desc: 'Genesis record with authoritative document SHA-256 checksum' },
  { event: 'EXTRACTION_COMPLETED', desc: 'Gemini extraction result, schema version, and model provenance' },
  { event: 'FORENSIC_ANALYSIS_COMPLETED', desc: 'Deterministic rule execution output and finding count' },
  { event: 'COMPLIANCE_ANALYSIS_COMPLETED', desc: 'POL-FIN-001 policy status and control mapping' },
  { event: 'RISK_ASSESSMENT_COMPLETED', desc: 'Composite risk score and dimensional calculation trace' },
  { event: 'AUDIT_SEALED', desc: 'Merkle root computation and immutable ledger closure' },
];

export const AuditPanel: React.FC<AuditPanelProps> = ({ workflow }) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>
      <div className="card">
        <div className="card-header">
          <div>
            <h3>Cryptographic Audit Ledger & Provenance</h3>
            <div style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)' }}>
              SHA-256 Linked Event Chain · Canonical JSON Serialization · Merkle Sealing
            </div>
          </div>
          {workflow && (
            <StatusBadge
              status={
                ['AUDIT_SEALED', 'REPORT_GENERATED', 'COMPLETED'].includes(workflow.current_state)
                  ? 'SEALED'
                  : 'RECORDING'
              }
              type="state"
            />
          )}
        </div>

        <div className="card-body">
          <div className="info-notice section-gap">
            <span className="notice-icon">🔗</span>
            <div>
              <strong>Cryptographic Chain Guarantees:</strong> Every state transition generates a canonically serialized audit event containing the SHA-256 hash of its payload and the hash of the preceding event. Any retrospective modification invalidates downstream hashes.
            </div>
          </div>

          <div className="detail-grid section-gap">
            <div className="detail-item">
              <span className="detail-label">Hashing Algorithm</span>
              <span className="detail-value mono">SHA-256</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Genesis Anchor</span>
              <span className="detail-value mono" style={{ fontSize: '0.75rem' }}>
                0000000000000000000000000000000000000000000000000000000000000000
              </span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Active Workflow Chain</span>
              <span className="detail-value mono">{workflow?.workflow_id || 'None'}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">State Monotonicity</span>
              <span className="detail-value mono">rev-{workflow?.workflow_revision || 1}</span>
            </div>
          </div>

          <div className="detail-label" style={{ marginBottom: 'var(--space-sm)' }}>
            Sequential Audit Event Chain Sequence
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Event Sequence</th>
                <th>Audit Event Type</th>
                <th>Cryptographic Payload Content</th>
              </tr>
            </thead>
            <tbody>
              {AUDIT_EVENT_TYPES.map((e, idx) => (
                <tr key={e.event}>
                  <td>
                    <span className="mono" style={{ fontWeight: 600 }}>
                      Block #{idx + 1}
                    </span>
                  </td>
                  <td>
                    <span className="badge badge-info">{e.event}</span>
                  </td>
                  <td style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>
                    {e.desc}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
