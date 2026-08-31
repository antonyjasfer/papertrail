import React from 'react';
import type { WorkflowDiagnostics, WorkflowStatus } from '../types/api';
import { formatDate } from '../utils/format';
import { StatusBadge } from './StatusBadge';

interface WorkflowTrackerProps {
  workflow: WorkflowStatus | null;
  diagnostics?: WorkflowDiagnostics | null;
  isPolling?: boolean;
}

const STAGES = [
  { id: 'UPLOADED', label: '1. Document Ingestion', desc: 'Secure payload storage & SHA-256 verification' },
  { id: 'EXTRACTING', label: '2. Gemini Extraction', desc: 'Multimodal structured entity extraction via Google GenAI SDK' },
  { id: 'EXTRACTED', label: '3. Classification & Normalization', desc: 'Financial schema mapping and confidence assessment' },
  { id: 'FORENSIC_ANALYSIS', label: '4. Deterministic Forensics', desc: 'Exact Decimal arithmetic, checksum & duplicate checks' },
  { id: 'COMPLIANCE_ANALYSIS', label: '5. Compliance Evaluation', desc: 'Policy POL-FIN-001 control verification' },
  { id: 'RISK_ASSESSED', label: '6. Multi-Dimensional Risk', desc: 'Composite scoring across 5 weighted dimensions' },
  { id: 'AUDIT_SEALED', label: '7. Cryptographic Audit', desc: 'SHA-256 event chaining & Merkle evidence sealing' },
  { id: 'REPORT_GENERATED', label: '8. Evidence Report', desc: 'Deterministic tamper-evident PDF/JSON summary' },
  { id: 'COMPLETED', label: '9. Autonomous Routing', desc: 'Final resolution: Auto-Approved or Escalated' },
];

export const WorkflowTracker: React.FC<WorkflowTrackerProps> = ({
  workflow,
  diagnostics,
  isPolling,
}) => {
  if (!workflow) {
    return (
      <div className="empty-state">
        <div className="empty-icon">⚡</div>
        <h3>No Active Workflow</h3>
        <p>Upload a document and start analysis to view the live execution pipeline.</p>
      </div>
    );
  }

  const currentState = workflow.current_state;

  // Determine stage status based on ordered state progression
  const stateOrder = [
    'UPLOADED',
    'INGESTING',
    'EXTRACTING',
    'EXTRACTED',
    'FORENSIC_ANALYSIS',
    'COMPLIANCE_ANALYSIS',
    'RISK_ASSESSED',
    'AUDIT_SEALED',
    'REPORT_GENERATED',
    'COMPLETED',
  ];

  const currentIndex = stateOrder.indexOf(currentState);

  const getStageStatus = (stageId: string, idx: number): 'completed' | 'active' | 'pending' | 'review' | 'failed' => {
    if (currentState === 'FAILED' || currentState === 'ESCALATED') {
      if (idx <= (currentIndex === -1 ? 0 : currentIndex)) return 'failed';
      return 'pending';
    }
    if (currentState === 'REQUIRES_REVIEW') {
      // Forensics/Risk/Routing triggered review
      if (idx < 6) return 'completed';
      if (idx === 6 || idx === 8) return 'review';
      return 'pending';
    }
    if (currentState === 'COMPLETED') {
      return 'completed';
    }

    const stageIdx = stateOrder.indexOf(stageId);
    if (currentIndex > stageIdx) return 'completed';
    if (currentIndex === stageIdx) return 'active';
    return 'pending';
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>
      {/* Workflow Header Card */}
      <div className="card">
        <div className="card-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <h3>Workflow Execution</h3>
            <span className="mono" style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--color-accent)' }}>
              {workflow.workflow_id}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {isPolling && (
              <span
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  fontSize: '0.75rem',
                  color: 'var(--color-info)',
                }}
              >
                <span className="loading-spinner" style={{ width: '12px', height: '12px' }} />
                Polling live state...
              </span>
            )}
            <StatusBadge status={currentState} type="state" />
          </div>
        </div>

        <div className="card-body">
          <div className="detail-grid">
            <div className="detail-item">
              <span className="detail-label">Current State</span>
              <span className="detail-value" style={{ fontWeight: 700 }}>
                {currentState}
              </span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Workflow Revision</span>
              <span className="detail-value mono">rev-{workflow.workflow_revision}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Document ID</span>
              <span className="detail-value mono">{workflow.document_id}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">Last State Transition</span>
              <span className="detail-value">{formatDate(workflow.updated_at)}</span>
            </div>
          </div>

          {/* Autonomous Routing / Review / Failure Banner */}
          {workflow.review_reason && (
            <div
              style={{
                marginTop: 'var(--space-md)',
                padding: 'var(--space-md)',
                background: 'var(--color-warning-bg)',
                border: '1px solid #fbd38d',
                borderRadius: 'var(--radius-md)',
                color: '#744210',
              }}
            >
              <div style={{ fontWeight: 700, fontSize: '0.85rem', marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span>⚠</span> Autonomous Routing Decision: Escalated to Human Review
              </div>
              <div style={{ fontSize: '0.8rem', lineHeight: 1.5 }}>
                {workflow.review_reason}
              </div>
            </div>
          )}

          {workflow.failure_reason && (
            <div
              style={{
                marginTop: 'var(--space-md)',
                padding: 'var(--space-md)',
                background: 'var(--color-error-bg)',
                border: '1px solid #feb2b2',
                borderRadius: 'var(--radius-md)',
                color: 'var(--color-error)',
              }}
            >
              <div style={{ fontWeight: 700, fontSize: '0.85rem', marginBottom: '4px' }}>
                ✕ Pipeline Failure Reason:
              </div>
              <div style={{ fontSize: '0.8rem' }}>{workflow.failure_reason}</div>
            </div>
          )}

          {currentState === 'COMPLETED' && !workflow.review_reason && (
            <div
              style={{
                marginTop: 'var(--space-md)',
                padding: 'var(--space-md)',
                background: 'var(--color-success-bg)',
                border: '1px solid #9ae6b4',
                borderRadius: 'var(--radius-md)',
                color: '#22543d',
              }}
            >
              <div style={{ fontWeight: 700, fontSize: '0.85rem', marginBottom: '2px' }}>
                ✓ Autonomous Decision: Auto-Approved
              </div>
              <div style={{ fontSize: '0.8rem' }}>
                All forensic and compliance criteria met with low risk profile. Evidence sealed in cryptographic audit ledger.
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Pipeline Stage Timeline */}
      <div className="card">
        <div className="card-header">
          <h3>Deterministic Stage Progression</h3>
          <span style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)' }}>
            Sequential event-driven execution with monotonic revision locking
          </span>
        </div>
        <div className="card-body">
          <div className="pipeline-stages">
            {STAGES.map((stage, idx) => {
              const status = getStageStatus(stage.id, idx);
              return (
                <div className="pipeline-stage" key={stage.id}>
                  <div className={`stage-indicator ${status}`}>
                    {status === 'completed' ? '✓' : status === 'review' ? '!' : status === 'failed' ? '✕' : idx + 1}
                  </div>
                  <div className="stage-content">
                    <div className={`stage-name ${status === 'pending' ? 'pending' : ''}`}>
                      {stage.label}
                    </div>
                    <div className="stage-meta">{stage.desc}</div>
                  </div>
                  <div style={{ marginLeft: 'auto', alignSelf: 'center' }}>
                    <StatusBadge
                      status={
                        status === 'completed'
                          ? 'COMPLETED'
                          : status === 'active'
                          ? 'RUNNING'
                          : status === 'review'
                          ? 'REVIEW'
                          : status === 'failed'
                          ? 'FAILED'
                          : 'PENDING'
                      }
                      type="state"
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Diagnostics Panel (if available) */}
      {diagnostics && (
        <div className="card">
          <div className="card-header">
            <h3>Operational Diagnostics</h3>
            <span style={{ fontSize: '0.75rem', color: diagnostics.is_stuck ? 'var(--color-error)' : 'var(--color-success)' }}>
              {diagnostics.is_stuck ? '⚠️ Stalled Workflow Detected' : '✓ Normal Execution Rhythm'}
            </span>
          </div>
          <div className="card-body">
            <div className="detail-grid">
              <div className="detail-item">
                <span className="detail-label">Stuck Detection</span>
                <span className="detail-value">{diagnostics.is_stuck ? 'Yes (Exceeded TTL)' : 'No'}</span>
              </div>
              <div className="detail-item">
                <span className="detail-label">Verified Revision</span>
                <span className="detail-value mono">rev-{diagnostics.workflow_revision}</span>
              </div>
            </div>
            {diagnostics.diagnostic_report && (
              <pre
                style={{
                  marginTop: 'var(--space-md)',
                  padding: 'var(--space-md)',
                  background: 'var(--color-bg-card-alt)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '0.75rem',
                  overflowX: 'auto',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                {JSON.stringify(diagnostics.diagnostic_report, null, 2)}
              </pre>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
