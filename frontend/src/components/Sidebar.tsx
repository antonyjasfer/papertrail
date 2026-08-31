import React from 'react';
import type { SystemHealthState } from '../hooks/useHealth';

export type PageId =
  | 'overview'
  | 'documents'
  | 'pipeline'
  | 'compliance'
  | 'risk'
  | 'review'
  | 'audit'
  | 'reports';

interface SidebarProps {
  currentPage: PageId;
  onNavigate: (page: PageId) => void;
  health: SystemHealthState;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentPage,
  onNavigate,
  health,
}) => {
  const navItems: { id: PageId; label: string; icon: string }[] = [
    { id: 'overview', label: 'Overview', icon: '📊' },
    { id: 'documents', label: 'Documents', icon: '📄' },
    { id: 'pipeline', label: 'Analysis Pipeline', icon: '⚡' },
    { id: 'compliance', label: 'Compliance', icon: '⚖️' },
    { id: 'risk', label: 'Risk Center', icon: '🛡️' },
    { id: 'review', label: 'Review Queue', icon: '📋' },
    { id: 'audit', label: 'Audit Ledger', icon: '🔗' },
    { id: 'reports', label: 'Reports', icon: '📑' },
  ];

  const getDepDot = (status?: string) => {
    if (!health.isConnected) return 'unknown';
    if (!status) return 'unknown';
    if (status === 'configured' || status === 'ready') return 'ok';
    if (status === 'unconfigured') return 'warn';
    return 'error';
  };

  const provider = health.readiness?.provider?.toUpperCase() || 'OFFLINE';

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div
            style={{
              width: '24px',
              height: '24px',
              borderRadius: '4px',
              background: '#2b7de9',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: '700',
              fontSize: '12px',
              color: '#fff',
            }}
          >
            P
          </div>
          <h1>PAPERTRAIL AI</h1>
        </div>
        <div className="brand-sub">Autonomous Document Intelligence</div>
      </div>

      <nav className="sidebar-nav">
        <div className="sidebar-section-label">Operations</div>
        {navItems.map((item) => (
          <button
            key={item.id}
            className={`sidebar-link ${currentPage === item.id ? 'active' : ''}`}
            onClick={() => onNavigate(item.id)}
          >
            <span className="icon">{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className="sidebar-section-label" style={{ padding: '0 0 8px 0' }}>
          System Readiness ({provider})
        </div>

        <div className="health-row">
          <span className={`health-dot ${health.isConnected ? 'ok' : 'error'}`} />
          <span>API Gateway</span>
          <span style={{ marginLeft: 'auto', fontSize: '0.7rem', opacity: 0.8 }}>
            {health.isConnected ? 'Ready' : 'Offline'}
          </span>
        </div>

        {health.readiness?.dependencies &&
          Object.entries(health.readiness.dependencies).map(([dep, status]) => (
            <div className="health-row" key={dep}>
              <span className={`health-dot ${getDepDot(status)}`} />
              <span style={{ textTransform: 'capitalize' }}>
                {dep.replace(/_/g, ' ')}
              </span>
              <span style={{ marginLeft: 'auto', fontSize: '0.7rem', opacity: 0.8 }}>
                {status}
              </span>
            </div>
          ))}

        <div
          style={{
            marginTop: '12px',
            paddingTop: '8px',
            borderTop: '1px solid #1a2836',
            fontSize: '0.7rem',
            color: '#627289',
            display: 'flex',
            justifyContent: 'space-between',
          }}
        >
          <span>v{health.health?.version || '0.1.0'}</span>
          <span>{health.readiness?.environment || 'dev'}</span>
        </div>
      </div>
    </aside>
  );
};
