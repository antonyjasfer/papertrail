import { useEffect, useState } from 'react';
import { Layout } from './components/Layout';
import type { PageId } from './components/Sidebar';
import { useHealth } from './hooks/useHealth';
import { useWorkflowPolling } from './hooks/useWorkflowPolling';
import { AuditPage } from './pages/AuditPage';
import { DocumentPage } from './pages/DocumentPage';
import { OverviewPage } from './pages/OverviewPage';
import { PipelinePage } from './pages/PipelinePage';
import { ReportsPage } from './pages/ReportsPage';
import { ReviewPage } from './pages/ReviewPage';
import type { DocumentResponse, WorkflowStatus } from './types/api';

export function App() {
  const [currentPage, setCurrentPage] = useState<PageId>('overview');
  const [activeWorkflowId, setActiveWorkflowId] = useState<string | null>(null);
  const [recentWorkflows, setRecentWorkflows] = useState<WorkflowStatus[]>([]);
  const [reviewWorkflows, setReviewWorkflows] = useState<WorkflowStatus[]>([]);

  const health = useHealth(10000);
  const {
    workflow,
    diagnostics,
    isPolling,
    startPolling,
    refetch,
  } = useWorkflowPolling(activeWorkflowId || undefined);

  // When active workflow changes or updates, keep lists in sync
  useEffect(() => {
    if (workflow) {
      setRecentWorkflows((prev) => {
        const filtered = prev.filter((w) => w.workflow_id !== workflow.workflow_id);
        return [workflow, ...filtered];
      });

      if (workflow.current_state === 'REQUIRES_REVIEW') {
        setReviewWorkflows((prev) => {
          const filtered = prev.filter((w) => w.workflow_id !== workflow.workflow_id);
          return [workflow, ...filtered];
        });
      } else {
        setReviewWorkflows((prev) =>
          prev.filter((w) => w.workflow_id !== workflow.workflow_id)
        );
      }
    }
  }, [workflow]);

  const handleWorkflowStarted = (wf: WorkflowStatus, _doc: DocumentResponse) => {
    setActiveWorkflowId(wf.workflow_id);
    startPolling(wf.workflow_id);
    setCurrentPage('pipeline');
  };

  const handleSelectWorkflow = (workflowId: string) => {
    setActiveWorkflowId(workflowId);
    startPolling(workflowId);
  };

  const handleWorkflowUpdated = (updated: WorkflowStatus) => {
    setRecentWorkflows((prev) =>
      prev.map((w) => (w.workflow_id === updated.workflow_id ? updated : w))
    );
    if (updated.current_state !== 'REQUIRES_REVIEW') {
      setReviewWorkflows((prev) =>
        prev.filter((w) => w.workflow_id !== updated.workflow_id)
      );
    }
  };

  const pageMeta: Record<PageId, { title: string; subtitle: string }> = {
    overview: {
      title: 'Overview',
      subtitle: 'Autonomous financial document intelligence dashboard',
    },
    documents: {
      title: 'Document Intelligence',
      subtitle: 'Analyze financial documents for fraud indicators, compliance violations, and risk',
    },
    pipeline: {
      title: 'Analysis Pipeline',
      subtitle: 'Live multi-stage execution with deterministic revision progression',
    },
    compliance: {
      title: 'Compliance Evaluation',
      subtitle: 'Organizational policy control verification (POL-FIN-001)',
    },
    risk: {
      title: 'Risk Center',
      subtitle: 'Multi-dimensional composite scoring & autonomous routing logic',
    },
    review: {
      title: 'Review Queue',
      subtitle: 'Human auditor workbench for escalated workflows',
    },
    audit: {
      title: 'Cryptographic Audit Ledger',
      subtitle: 'Immutable SHA-256 linked event chain & Merkle evidence sealing',
    },
    reports: {
      title: 'Reports & Artifacts',
      subtitle: 'Tamper-evident audit bundles and document artifact retrieval',
    },
  };

  const meta = pageMeta[currentPage];

  return (
    <Layout
      currentPage={currentPage}
      onNavigate={setCurrentPage}
      health={health}
      activeWorkflowId={activeWorkflowId}
      pageTitle={meta.title}
      pageSubtitle={meta.subtitle}
    >
      {currentPage === 'overview' && (
        <OverviewPage
          onNavigate={setCurrentPage}
          health={health}
          recentWorkflows={recentWorkflows}
          onSelectWorkflow={handleSelectWorkflow}
        />
      )}

      {currentPage === 'documents' && (
        <DocumentPage onWorkflowStarted={handleWorkflowStarted} />
      )}

      {currentPage === 'pipeline' && (
        <PipelinePage
          workflow={workflow}
          diagnostics={diagnostics}
          isPolling={isPolling}
          onRefresh={refetch}
          onSelectWorkflowId={handleSelectWorkflow}
        />
      )}

      {currentPage === 'compliance' && (
        <PipelinePage
          workflow={workflow}
          diagnostics={diagnostics}
          isPolling={isPolling}
          onRefresh={refetch}
          onSelectWorkflowId={handleSelectWorkflow}
        />
      )}

      {currentPage === 'risk' && (
        <PipelinePage
          workflow={workflow}
          diagnostics={diagnostics}
          isPolling={isPolling}
          onRefresh={refetch}
          onSelectWorkflowId={handleSelectWorkflow}
        />
      )}

      {currentPage === 'review' && (
        <ReviewPage
          reviewWorkflows={reviewWorkflows}
          onWorkflowUpdated={handleWorkflowUpdated}
        />
      )}

      {currentPage === 'audit' && <AuditPage workflow={workflow} />}

      {currentPage === 'reports' && <ReportsPage workflow={workflow} />}
    </Layout>
  );
}

export default App;
