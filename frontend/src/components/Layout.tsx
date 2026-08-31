import React from 'react';
import type { SystemHealthState } from '../hooks/useHealth';
import { Sidebar, type PageId } from './Sidebar';
import { StatusBadge } from './StatusBadge';

interface LayoutProps {
  currentPage: PageId;
  onNavigate: (page: PageId) => void;
  health: SystemHealthState & { refresh: () => Promise<void> };
  activeWorkflowId?: string | null;
  children: React.ReactNode;
  pageTitle: string;
  pageSubtitle?: string;
}

export const Layout: React.FC<LayoutProps> = ({
  currentPage,
  onNavigate,
  health,
  activeWorkflowId,
  children,
  pageTitle,
  pageSubtitle,
}) => {
  return (
    <div className="app-layout">
      <Sidebar
        currentPage={currentPage}
        onNavigate={onNavigate}
        health={health}
      />

      <main className="main-content">
        <header className="page-header">
          <div>
            <h1>{pageTitle}</h1>
            {pageSubtitle && <div className="subtitle">{pageSubtitle}</div>}
          </div>

          <div className="page-header-right">
            {activeWorkflowId && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  background: '#f0f4f9',
                  padding: '4px 12px',
                  borderRadius: '6px',
                  border: '1px solid #d5e2f0',
                  fontSize: '0.8rem',
                }}
              >
                <span style={{ color: '#5a6577', fontWeight: 600 }}>Active:</span>
                <span className="mono" style={{ color: '#1a202c', fontWeight: 600 }}>
                  {activeWorkflowId}
                </span>
              </div>
            )}

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <StatusBadge
                status={health.isConnected ? (health.readiness?.provider || 'API READY') : 'OFFLINE'}
                type="health"
              />
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => health.refresh()}
                title="Refresh system status"
              >
                ↻
              </button>
            </div>

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                paddingLeft: '12px',
                borderLeft: '1px solid var(--color-border)',
                fontSize: '0.8rem',
              }}
            >
              <div
                style={{
                  width: '28px',
                  height: '28px',
                  borderRadius: '50%',
                  background: '#e2e8f0',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 600,
                  fontSize: '0.75rem',
                  color: '#475569',
                }}
              >
                RP
              </div>
              <div>
                <div style={{ fontWeight: 600, fontSize: '0.75rem' }}>Reviewer Principal</div>
                <div style={{ fontSize: '0.68rem', color: 'var(--color-text-tertiary)' }}>
                  sec-auditor-01
                </div>
              </div>
            </div>
          </div>
        </header>

        <div className="page-body">{children}</div>
      </main>
    </div>
  );
};
