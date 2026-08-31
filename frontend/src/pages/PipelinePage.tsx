import React, { useState } from 'react';
import { AuditPanel } from '../components/AuditPanel';
import { CompliancePanel } from '../components/CompliancePanel';
import { ExtractionPanel } from '../components/ExtractionPanel';
import { ForensicPanel } from '../components/ForensicPanel';
import { RiskPanel } from '../components/RiskPanel';
import { WorkflowTracker } from '../components/WorkflowTracker';
import type { WorkflowDiagnostics, WorkflowStatus } from '../types/api';

type SubTab = 'stages' | 'extraction' | 'forensics' | 'compliance' | 'risk' | 'audit';

interface PipelinePageProps {
  workflow: WorkflowStatus | null;
  diagnostics: WorkflowDiagnostics | null;
  isPolling: boolean;
  onRefresh: () => void;
  onSelectWorkflowId: (id: string) => void;
}

export const PipelinePage: React.FC<PipelinePageProps> = ({
  workflow,
  diagnostics,
  isPolling,
  onRefresh,
  onSelectWorkflowId,
}) => {
  const [activeTab, setActiveTab] = useState<SubTab>('stages');
  const [lookupInput, setLookupInput] = useState<string>('');

  const tabs: { id: SubTab; label: string }[] = [
    { id: 'stages', label: '1. Pipeline Stages' },
    { id: 'extraction', label: '2. Gemini Extraction' },
    { id: 'forensics', label: '3. Forensic Findings' },
    { id: 'compliance', label: '4. Compliance (POL-FIN-001)' },
    { id: 'risk', label: '5. Risk Assessment' },
    { id: 'audit', label: '6. Cryptographic Audit' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>
      {/* Search / Lookup Bar */}
      <div
        className="card"
        style={{
          padding: 'var(--space-md) var(--space-lg)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1 }}>
          <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>Lookup Workflow:</span>
          <input
            type="text"
            className="mono"
            placeholder="e.g. wf-7f1a8c9b"
            value={lookupInput}
            onChange={(e) => setLookupInput(e.target.value)}
            style={{
              padding: '6px 12px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--color-border)',
              fontSize: '0.85rem',
              width: '240px',
            }}
          />
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => {
              if (lookupInput.trim()) {
                onSelectWorkflowId(lookupInput.trim());
              }
            }}
          >
            Load
          </button>
        </div>

        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn btn-secondary btn-sm" onClick={onRefresh}>
            ↻ Refresh State
          </button>
        </div>
      </div>

      {/* Sub-Navigation Tabs */}
      <div
        style={{
          display: 'flex',
          gap: '4px',
          borderBottom: '1px solid var(--color-border)',
          paddingBottom: '2px',
        }}
      >
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            style={{
              padding: '8px 16px',
              background: activeTab === t.id ? 'var(--color-bg-card)' : 'transparent',
              border: '1px solid',
              borderColor: activeTab === t.id ? 'var(--color-border)' : 'transparent',
              borderBottomColor: activeTab === t.id ? 'var(--color-bg-card)' : 'transparent',
              borderRadius: 'var(--radius-sm) var(--radius-sm) 0 0',
              fontWeight: activeTab === t.id ? 700 : 500,
              color: activeTab === t.id ? 'var(--color-accent)' : 'var(--color-text-secondary)',
              cursor: 'pointer',
              fontSize: '0.85rem',
              marginBottom: '-3px',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab Panels */}
      {activeTab === 'stages' && (
        <WorkflowTracker
          workflow={workflow}
          diagnostics={diagnostics}
          isPolling={isPolling}
        />
      )}

      {activeTab === 'extraction' && <ExtractionPanel workflow={workflow} />}

      {activeTab === 'forensics' && <ForensicPanel workflow={workflow} />}

      {activeTab === 'compliance' && <CompliancePanel workflow={workflow} />}

      {activeTab === 'risk' && <RiskPanel workflow={workflow} />}

      {activeTab === 'audit' && <AuditPanel workflow={workflow} />}
    </div>
  );
};
