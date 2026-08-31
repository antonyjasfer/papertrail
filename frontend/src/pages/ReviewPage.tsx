import React, { useState } from 'react';
import { StatusBadge } from '../components/StatusBadge';
import { apiClient } from '../services/apiClient';
import type { WorkflowStatus } from '../types/api';
import { formatDate } from '../utils/format';

interface ReviewPageProps {
  reviewWorkflows: WorkflowStatus[];
  onWorkflowUpdated: (updated: WorkflowStatus) => void;
}

export const ReviewPage: React.FC<ReviewPageProps> = ({
  reviewWorkflows,
  onWorkflowUpdated,
}) => {
  const [selectedWf, setSelectedWf] = useState<WorkflowStatus | null>(
    reviewWorkflows.length > 0 ? reviewWorkflows[0] : null
  );

  const [reviewerPrincipal, setReviewerPrincipal] = useState<string>('sec-auditor-01');
  const [decision, setDecision] = useState<'APPROVED' | 'REJECTED' | 'RE_EVALUATE'>('APPROVED');
  const [decisionReason, setDecisionReason] = useState<string>('Verified supporting invoice evidence against external vendor ledger.');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  const handleResume = async () => {
    if (!selectedWf) return;
    setIsSubmitting(true);
    setActionError(null);
    setActionSuccess(null);

    const requestedTarget =
      decision === 'APPROVED'
        ? 'COMPLETED'
        : decision === 'REJECTED'
        ? 'FAILED'
        : 'FORENSIC_ANALYSIS';

    try {
      const updated = await apiClient.resumePipeline(
        selectedWf.workflow_id,
        {
          reviewer_id: reviewerPrincipal,
          decision,
          decision_reason: decisionReason,
          requested_target: requestedTarget,
        },
        reviewerPrincipal
      );

      setActionSuccess(`Workflow resumed successfully: Transitioned to ${updated.current_state} (rev-${updated.workflow_revision})`);
      setSelectedWf(updated);
      onWorkflowUpdated(updated);
    } catch (err) {
      setActionError((err as Error).message || 'Failed to resume workflow');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>
      {/* Review Header Banner */}
      <div className="card">
        <div className="card-header">
          <div>
            <h3>Human Review Workbench</h3>
            <div style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)' }}>
              Escalated workflows requiring human auditor authorization · Authenticated resume action
            </div>
          </div>
          <span className="badge badge-warning">
            {reviewWorkflows.length} Pending Review
          </span>
        </div>

        <div className="card-body">
          {reviewWorkflows.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">✓</div>
              <h3>Review Queue Clear</h3>
              <p>No workflows currently pending human review. Clean invoices with low risk scores are auto-approved.</p>
            </div>
          ) : (
            <div className="grid-2">
              {/* Queue List */}
              <div>
                <div className="detail-label" style={{ marginBottom: 'var(--space-sm)' }}>
                  Workflows Awaiting Review
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {reviewWorkflows.map((wf) => (
                    <div
                      key={wf.workflow_id}
                      onClick={() => {
                        setSelectedWf(wf);
                        setActionError(null);
                        setActionSuccess(null);
                      }}
                      style={{
                        padding: 'var(--space-md)',
                        borderRadius: 'var(--radius-md)',
                        border: '1px solid',
                        borderColor: selectedWf?.workflow_id === wf.workflow_id ? 'var(--color-accent)' : 'var(--color-border)',
                        background: selectedWf?.workflow_id === wf.workflow_id ? 'var(--color-info-bg)' : 'var(--color-bg-card)',
                        cursor: 'pointer',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                        <span className="mono" style={{ fontWeight: 700 }}>
                          {wf.workflow_id}
                        </span>
                        <StatusBadge status={wf.current_state} type="state" />
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)' }}>
                        Doc: <span className="mono">{wf.document_id}</span> · Updated {formatDate(wf.updated_at)}
                      </div>
                      {wf.review_reason && (
                        <div style={{ fontSize: '0.78rem', color: '#744210', marginTop: '6px' }}>
                          <strong>Reason:</strong> {wf.review_reason}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Review Actions Form */}
              {selectedWf && (
                <div
                  style={{
                    padding: 'var(--space-lg)',
                    background: 'var(--color-bg-card-alt)',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--color-border)',
                  }}
                >
                  <h4 style={{ marginBottom: 'var(--space-md)' }}>
                    Review Action: <span className="mono">{selectedWf.workflow_id}</span>
                  </h4>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}>
                    <div>
                      <label className="detail-label">Reviewer Principal (X-Reviewer-Principal)</label>
                      <input
                        type="text"
                        value={reviewerPrincipal}
                        onChange={(e) => setReviewerPrincipal(e.target.value)}
                        style={{
                          width: '100%',
                          padding: '8px 12px',
                          marginTop: '4px',
                          borderRadius: 'var(--radius-sm)',
                          border: '1px solid var(--color-border)',
                          fontFamily: 'var(--font-mono)',
                          fontSize: '0.85rem',
                        }}
                      />
                    </div>

                    <div>
                      <label className="detail-label">Decision</label>
                      <select
                        value={decision}
                        onChange={(e) => setDecision(e.target.value as any)}
                        style={{
                          width: '100%',
                          padding: '8px 12px',
                          marginTop: '4px',
                          borderRadius: 'var(--radius-sm)',
                          border: '1px solid var(--color-border)',
                          fontSize: '0.85rem',
                          background: '#fff',
                        }}
                      >
                        <option value="APPROVED">APPROVED (Resume to COMPLETED)</option>
                        <option value="REJECTED">REJECTED (Halt to FAILED)</option>
                        <option value="RE_EVALUATE">RE_EVALUATE (Re-run Forensic Analysis)</option>
                      </select>
                    </div>

                    <div>
                      <label className="detail-label">Auditor Justification / Notes</label>
                      <textarea
                        rows={3}
                        value={decisionReason}
                        onChange={(e) => setDecisionReason(e.target.value)}
                        style={{
                          width: '100%',
                          padding: '8px 12px',
                          marginTop: '4px',
                          borderRadius: 'var(--radius-sm)',
                          border: '1px solid var(--color-border)',
                          fontSize: '0.85rem',
                          fontFamily: 'var(--font-sans)',
                        }}
                      />
                    </div>

                    {actionError && (
                      <div
                        style={{
                          padding: 'var(--space-sm)',
                          background: 'var(--color-error-bg)',
                          border: '1px solid #fecaca',
                          borderRadius: 'var(--radius-sm)',
                          color: 'var(--color-error)',
                          fontSize: '0.8rem',
                        }}
                      >
                        {actionError}
                      </div>
                    )}

                    {actionSuccess && (
                      <div
                        style={{
                          padding: 'var(--space-sm)',
                          background: 'var(--color-success-bg)',
                          border: '1px solid #9ae6b4',
                          borderRadius: 'var(--radius-sm)',
                          color: '#22543d',
                          fontSize: '0.8rem',
                        }}
                      >
                        {actionSuccess}
                      </div>
                    )}

                    <button
                      className="btn btn-primary"
                      onClick={handleResume}
                      disabled={isSubmitting || selectedWf.current_state !== 'REQUIRES_REVIEW'}
                    >
                      {isSubmitting ? (
                        <>
                          <span className="loading-spinner" /> Resuming Pipeline...
                        </>
                      ) : (
                        `Authorize ${decision} & Resume Workflow`
                      )}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
