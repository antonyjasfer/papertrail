import React from 'react';
import type { PageId } from '../components/Sidebar';
import { StatusBadge } from '../components/StatusBadge';
import type { SystemHealthState } from '../hooks/useHealth';
import type { WorkflowStatus } from '../types/api';

interface OverviewPageProps {
  onNavigate: (page: PageId) => void;
  health: SystemHealthState;
  recentWorkflows: WorkflowStatus[];
  onSelectWorkflow: (workflowId: string) => void;
}

export const OverviewPage: React.FC<OverviewPageProps> = ({
  onNavigate,
  health,
  recentWorkflows,
  onSelectWorkflow,
}) => {
  const provider = health.readiness?.provider?.toUpperCase() || 'OFFLINE';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-xl)' }}>
      {/* Hero / Value Proposition Banner */}
      <div
        className="card"
        style={{
          background: 'linear-gradient(135deg, #0f1923 0%, #1a2d42 100%)',
          color: '#ffffff',
          border: '1px solid #1a2836',
        }}
      >
        <div className="card-body" style={{ padding: 'var(--space-xl)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div
                style={{
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '1px',
                  color: '#93c5fd',
                  marginBottom: '6px',
                }}
              >
                Autonomous Evidence Platform
              </div>
              <h2 style={{ fontSize: '1.6rem', color: '#ffffff', marginBottom: '8px' }}>
                PaperTrail Financial Intelligence
              </h2>
              <p style={{ color: '#94a3b8', maxWidth: '640px', fontSize: '0.9rem', lineHeight: 1.6 }}>
                Autonomous pipeline that extracts structured data, executes deterministic forensic rules,
                evaluates organizational compliance, calculates multi-dimensional risk, and cryptographically
                seals evidence.
              </p>
            </div>

            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                className="btn btn-primary btn-lg"
                onClick={() => onNavigate('documents')}
                style={{ background: '#2b7de9', borderColor: '#2b7de9' }}
              >
                📄 Analyze Document
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* KPI Stats Grid */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-label">Active Cloud Provider</div>
          <div className="kpi-value" style={{ fontSize: '1.4rem', color: 'var(--color-accent)' }}>
            {provider}
          </div>
          <div className="kpi-sub">
            {health.readiness?.environment || 'development'} environment
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">API Gateway Status</div>
          <div className="kpi-value" style={{ fontSize: '1.4rem' }}>
            <StatusBadge
              status={health.isConnected ? 'HEALTHY' : 'OFFLINE'}
              type="health"
            />
          </div>
          <div className="kpi-sub">
            {health.health?.service || 'PaperTrail AI'} v{health.health?.version || '0.1.0'}
          </div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">Document Intelligence</div>
          <div className="kpi-value" style={{ fontSize: '1.4rem' }}>
            Gemini 3.5+
          </div>
          <div className="kpi-sub">Google GenAI SDK · Zero-Fabrication</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-label">Forensic Engine</div>
          <div className="kpi-value" style={{ fontSize: '1.4rem' }}>
            8 Rules
          </div>
          <div className="kpi-sub">Exact Decimal · Pure Python</div>
        </div>
      </div>

      {/* 2-Column: Recent Workflows & Pipeline Flow */}
      <div className="grid-2">
        {/* Recent Workflows */}
        <div className="card">
          <div className="card-header">
            <h3>Recent Analysis Workflows</h3>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => onNavigate('pipeline')}
            >
              View Pipeline
            </button>
          </div>
          <div className="card-body" style={{ padding: 0 }}>
            {recentWorkflows.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">📄</div>
                <p>No workflows initiated in this session yet.</p>
                <button
                  className="btn btn-primary btn-sm"
                  style={{ marginTop: '12px' }}
                  onClick={() => onNavigate('documents')}
                >
                  Upload & Analyze Document
                </button>
              </div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Workflow ID</th>
                    <th>Document</th>
                    <th>State</th>
                    <th>Revision</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {recentWorkflows.map((wf) => (
                    <tr key={wf.workflow_id}>
                      <td className="mono" style={{ fontWeight: 600 }}>
                        {wf.workflow_id}
                      </td>
                      <td className="mono" style={{ fontSize: '0.75rem' }}>
                        {wf.document_id}
                      </td>
                      <td>
                        <StatusBadge status={wf.current_state} type="state" />
                      </td>
                      <td className="mono">rev-{wf.workflow_revision}</td>
                      <td>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => {
                            onSelectWorkflow(wf.workflow_id);
                            onNavigate('pipeline');
                          }}
                        >
                          Track
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* How PaperTrail Works */}
        <div className="card">
          <div className="card-header">
            <h3>Autonomous Execution Architecture</h3>
          </div>
          <div className="card-body">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '0.85rem' }}>
              <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                <div
                  style={{
                    width: '24px',
                    height: '24px',
                    borderRadius: '50%',
                    background: '#e0edff',
                    color: '#2b7de9',
                    fontWeight: 700,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                    fontSize: '0.75rem',
                  }}
                >
                  1
                </div>
                <div>
                  <div style={{ fontWeight: 600 }}>Document Ingestion & Checksum</div>
                  <div style={{ color: 'var(--color-text-secondary)', fontSize: '0.78rem' }}>
                    Authoritative SHA-256 calculation and immutable payload storage.
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                <div
                  style={{
                    width: '24px',
                    height: '24px',
                    borderRadius: '50%',
                    background: '#e0edff',
                    color: '#2b7de9',
                    fontWeight: 700,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                    fontSize: '0.75rem',
                  }}
                >
                  2
                </div>
                <div>
                  <div style={{ fontWeight: 600 }}>Gemini 3.5 Multimodal Extraction</div>
                  <div style={{ color: 'var(--color-text-secondary)', fontSize: '0.78rem' }}>
                    Structured schema extraction with confidence scoring and fail-closed safety.
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                <div
                  style={{
                    width: '24px',
                    height: '24px',
                    borderRadius: '50%',
                    background: '#e0edff',
                    color: '#2b7de9',
                    fontWeight: 700,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                    fontSize: '0.75rem',
                  }}
                >
                  3
                </div>
                <div>
                  <div style={{ fontWeight: 600 }}>Deterministic Forensic & Compliance Rules</div>
                  <div style={{ color: 'var(--color-text-secondary)', fontSize: '0.78rem' }}>
                    Exact Decimal verification of line items, totals, dates, and historical duplicates.
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                <div
                  style={{
                    width: '24px',
                    height: '24px',
                    borderRadius: '50%',
                    background: '#e0edff',
                    color: '#2b7de9',
                    fontWeight: 700,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                    fontSize: '0.75rem',
                  }}
                >
                  4
                </div>
                <div>
                  <div style={{ fontWeight: 600 }}>Risk Scoring & Cryptographic Audit Seal</div>
                  <div style={{ color: 'var(--color-text-secondary)', fontSize: '0.78rem' }}>
                    Multi-dimensional risk score, autonomous routing, and SHA-256 hash chaining.
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
