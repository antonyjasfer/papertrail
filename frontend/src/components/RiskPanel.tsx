import React from 'react';
import type { WorkflowStatus } from '../types/api';
import { StatusBadge } from './StatusBadge';

interface RiskPanelProps {
  workflow: WorkflowStatus | null;
}

const RISK_DIMENSIONS = [
  { name: 'Forensic Risk', weight: '35%', desc: 'Severity-weighted sum of deterministic forensic rule violations.' },
  { name: 'Compliance Risk', weight: '25%', desc: 'Policy control failures under POL-FIN-001.' },
  { name: 'Extraction Quality', weight: '15%', desc: 'Gemini multimodal model confidence and payload consistency.' },
  { name: 'Provenance Integrity', weight: '15%', desc: 'Storage metadata consistency and header integrity.' },
  { name: 'Data Completeness', weight: '10%', desc: 'Presence of mandatory invoice entities and line items.' },
];

export const RiskPanel: React.FC<RiskPanelProps> = ({ workflow }) => {
  const isReview = workflow?.current_state === 'REQUIRES_REVIEW';
  const isCompleted = workflow?.current_state === 'COMPLETED';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>
      {/* Risk Summary Card */}
      <div className="card">
        <div className="card-header">
          <div>
            <h3>Multi-Dimensional Risk Assessment</h3>
            <div style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)' }}>
              Deterministic composite scoring across 5 weighted dimensions · Zero LLM dependencies
            </div>
          </div>
          {workflow && (
            <StatusBadge
              status={isReview ? 'HIGH / REVIEW' : isCompleted ? 'LOW / APPROVED' : 'CALCULATING'}
              type={isReview ? 'severity' : 'state'}
            />
          )}
        </div>

        <div className="card-body">
          <div className="grid-2 section-gap">
            <div
              style={{
                padding: 'var(--space-lg)',
                background: 'var(--color-bg-card-alt)',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--color-border)',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
              }}
            >
              <div className="detail-label">Autonomous Routing Decision</div>
              <div
                style={{
                  fontSize: '1.4rem',
                  fontWeight: 700,
                  marginTop: '4px',
                  color: isReview ? 'var(--color-warning)' : isCompleted ? 'var(--color-success)' : 'var(--color-text-primary)',
                }}
              >
                {isReview ? '⚠️ Escalated to Review' : isCompleted ? '✓ Auto-Approved' : 'Evaluating...'}
              </div>
              <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)', marginTop: '4px' }}>
                {isReview
                  ? 'Risk score or critical forensic findings exceeded automated approval thresholds.'
                  : isCompleted
                  ? 'All 5 dimensions within normal thresholds. Zero critical findings.'
                  : 'Awaiting pipeline progression.'}
              </div>
            </div>

            <div
              style={{
                padding: 'var(--space-lg)',
                background: 'var(--color-bg-card-alt)',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--color-border)',
              }}
            >
              <div className="detail-label">Score Threshold Boundaries</div>
              <div style={{ marginTop: '8px', display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.8rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--color-success)', fontWeight: 600 }}>LOW (0.00 – 25.00):</span>
                  <span>Autonomous Auto-Approval</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--color-warning)', fontWeight: 600 }}>MEDIUM (25.01 – 50.00):</span>
                  <span>Review Recommendation</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--color-high)', fontWeight: 600 }}>HIGH (50.01 – 75.00):</span>
                  <span>Mandatory Human Review</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--color-critical)', fontWeight: 600 }}>CRITICAL (75.01 – 100.00):</span>
                  <span>Immediate Escalation / Halt</span>
                </div>
              </div>
            </div>
          </div>

          <div className="detail-label" style={{ marginBottom: 'var(--space-sm)' }}>
            Dimensional Weight Distribution
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Dimension</th>
                <th>Weight</th>
                <th>Evaluation Description</th>
              </tr>
            </thead>
            <tbody>
              {RISK_DIMENSIONS.map((d) => (
                <tr key={d.name}>
                  <td style={{ fontWeight: 600 }}>{d.name}</td>
                  <td>
                    <span className="mono" style={{ fontWeight: 700 }}>
                      {d.weight}
                    </span>
                  </td>
                  <td style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>
                    {d.desc}
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
