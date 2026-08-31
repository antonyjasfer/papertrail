import React from 'react';
import type { WorkflowStatus } from '../types/api';
import { StatusBadge } from './StatusBadge';

interface ForensicPanelProps {
  workflow: WorkflowStatus | null;
}

const FORENSIC_RULES = [
  { id: 'R-FIN-001', name: 'Line Item Arithmetic Verification', category: 'Financial', severity: 'CRITICAL', desc: 'Verifies Decimal(quantity) × Decimal(unit_price) == Decimal(amount) for all line items.' },
  { id: 'R-FIN-002', name: 'Invoice Total Verification', category: 'Financial', severity: 'HIGH', desc: 'Verifies the sum of individual line item amounts equals the declared invoice total.' },
  { id: 'R-DUP-001', name: 'Duplicate Invoice Identifier', category: 'Duplicate', severity: 'CRITICAL', desc: 'Checks historical document repository for identical invoice numbers from the same vendor.' },
  { id: 'R-DUP-002', name: 'Duplicate Document SHA-256 Checksum', category: 'Duplicate', severity: 'CRITICAL', desc: 'Detects byte-for-byte identical file uploads across previous workflows.' },
  { id: 'R-STR-001', name: 'Missing Required Structural Fields', category: 'Structural', severity: 'HIGH', desc: 'Flags invoices missing mandatory business identifiers (number, vendor, date, total).' },
  { id: 'R-TMP-001', name: 'Future Dated Invoice Detection', category: 'Temporal', severity: 'MEDIUM', desc: 'Flags invoice dates set after the processing reference timestamp.' },
  { id: 'R-TMP-002', name: 'Temporal Validity & Range Conformance', category: 'Temporal', severity: 'MEDIUM', desc: 'Validates due dates occur on or after invoice issuance dates.' },
  { id: 'R-MET-001', name: 'Metadata & Content-Type Integrity', category: 'Metadata', severity: 'LOW', desc: 'Ensures declared file extension matches underlying magic byte content structure.' },
];

export const ForensicPanel: React.FC<ForensicPanelProps> = ({ workflow }) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>
      {/* Overview Card */}
      <div className="card">
        <div className="card-header">
          <div>
            <h3>Deterministic Forensic Engine</h3>
            <div style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)' }}>
              Pure Python Decimal arithmetic · Zero LLM dependencies · Zero database reads during rule execution
            </div>
          </div>
          {workflow && <StatusBadge status={workflow.current_state} type="state" />}
        </div>

        <div className="card-body">
          {workflow?.review_reason && (
            <div
              style={{
                marginBottom: 'var(--space-lg)',
                padding: 'var(--space-md)',
                background: 'var(--color-warning-bg)',
                border: '1px solid #fbd38d',
                borderRadius: 'var(--radius-md)',
              }}
            >
              <div style={{ fontWeight: 700, fontSize: '0.85rem', color: '#744210', marginBottom: '4px' }}>
                Forensic Engine Finding Summary:
              </div>
              <div style={{ fontSize: '0.82rem', color: '#744210' }}>
                {workflow.review_reason}
              </div>
            </div>
          )}

          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Rule ID</th>
                  <th>Rule Name</th>
                  <th>Category</th>
                  <th>Default Severity</th>
                  <th>Validation Logic</th>
                </tr>
              </thead>
              <tbody>
                {FORENSIC_RULES.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <span className="mono" style={{ fontWeight: 600 }}>
                        {r.id}
                      </span>
                    </td>
                    <td style={{ fontWeight: 500 }}>{r.name}</td>
                    <td>
                      <span className="badge badge-neutral">{r.category}</span>
                    </td>
                    <td>
                      <StatusBadge status={r.severity} type="severity" />
                    </td>
                    <td style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>
                      {r.desc}
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
