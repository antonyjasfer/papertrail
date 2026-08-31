import React from 'react';
import type { WorkflowStatus } from '../types/api';
import { StatusBadge } from './StatusBadge';

interface CompliancePanelProps {
  workflow: WorkflowStatus | null;
}

const COMPLIANCE_CONTROLS = [
  { id: 'C-FIN-001', name: 'Financial Arithmetic Accuracy', policy: 'POL-FIN-001', target: 'Line Item & Total Correctness', rules: 'R-FIN-001, R-FIN-002' },
  { id: 'C-FIN-002', name: 'Duplicate Payment Prevention', policy: 'POL-FIN-001', target: 'Historical Invoice & SHA-256 Collisions', rules: 'R-DUP-001, R-DUP-002' },
  { id: 'C-STR-001', name: 'Mandatory Metadata & Structural Integrity', policy: 'POL-FIN-001', target: 'Presence of Invoice Number, Dates, Parties', rules: 'R-STR-001' },
  { id: 'C-TMP-001', name: 'Temporal Sequence & Issuance Realism', policy: 'POL-FIN-001', target: 'Past issuance dates and valid chronological sequence', rules: 'R-TMP-001, R-TMP-002' },
  { id: 'C-MET-001', name: 'MIME Format & Magic-Byte Authenticity', policy: 'POL-FIN-001', target: 'Payload signature verification', rules: 'R-MET-001' },
];

export const CompliancePanel: React.FC<CompliancePanelProps> = ({ workflow }) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>
      <div className="card">
        <div className="card-header">
          <div>
            <h3>Compliance Evaluation (POL-FIN-001)</h3>
            <div style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)' }}>
              Invoice Financial Integrity Policy v1.0.0 · Deterministic policy mapping from forensic evidence
            </div>
          </div>
          {workflow && (
            <StatusBadge
              status={
                workflow.current_state === 'COMPLETED'
                  ? 'COMPLIANT'
                  : workflow.current_state === 'REQUIRES_REVIEW'
                  ? 'REQUIRES_REVIEW'
                  : 'EVALUATING'
              }
              type="state"
            />
          )}
        </div>

        <div className="card-body">
          <div className="info-notice section-gap">
            <span className="notice-icon">📋</span>
            <div>
              <strong>Deterministic Compliance Mapping:</strong> Compliance evaluation does not rely on subjective LLM evaluations. Findings from forensic rules are deterministically evaluated against versioned organizational policies.
            </div>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Control ID</th>
                  <th>Control Name</th>
                  <th>Policy</th>
                  <th>Verification Objective</th>
                  <th>Underlying Forensic Rules</th>
                </tr>
              </thead>
              <tbody>
                {COMPLIANCE_CONTROLS.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <span className="mono" style={{ fontWeight: 600 }}>
                        {c.id}
                      </span>
                    </td>
                    <td style={{ fontWeight: 500 }}>{c.name}</td>
                    <td>
                      <span className="badge badge-info">{c.policy}</span>
                    </td>
                    <td style={{ fontSize: '0.8rem' }}>{c.target}</td>
                    <td>
                      <span className="mono" style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)' }}>
                        {c.rules}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};
