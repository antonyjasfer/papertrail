import { useCallback, useEffect, useRef, useState } from 'react';
import { apiClient } from '../services/apiClient';
import type { WorkflowDiagnostics, WorkflowStatus } from '../types/api';
import { TERMINAL_STATES } from '../types/api';

interface UseWorkflowPollingReturn {
  workflow: WorkflowStatus | null;
  diagnostics: WorkflowDiagnostics | null;
  isLoading: boolean;
  isPolling: boolean;
  error: string | null;
  startPolling: (workflowId: string) => void;
  stopPolling: () => void;
  refetch: () => Promise<void>;
}

export function useWorkflowPolling(initialWorkflowId?: string): UseWorkflowPollingReturn {
  const [workflowId, setWorkflowId] = useState<string | undefined>(initialWorkflowId);
  const [workflow, setWorkflow] = useState<WorkflowStatus | null>(null);
  const [diagnostics, setDiagnostics] = useState<WorkflowDiagnostics | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isPolling, setIsPolling] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const pollIntervalRef = useRef<number | null>(null);

  const fetchStatus = useCallback(async (id: string) => {
    try {
      setError(null);
      const status = await apiClient.getPipelineStatus(id);
      setWorkflow(status);

      // If workflow has reached terminal state or review state, fetch diagnostics
      if (
        TERMINAL_STATES.includes(status.current_state as any) ||
        status.current_state === 'REQUIRES_REVIEW'
      ) {
        try {
          const diag = await apiClient.getWorkflowDiagnostics(id);
          setDiagnostics(diag);
        } catch {
          // Non-critical if diagnostics fetch fails
        }
      }

      // Check if we should stop polling
      if (
        TERMINAL_STATES.includes(status.current_state as any) ||
        status.current_state === 'REQUIRES_REVIEW'
      ) {
        setIsPolling(false);
        if (pollIntervalRef.current) {
          window.clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
      }
    } catch (err) {
      setError((err as Error).message || 'Failed to fetch workflow status');
      setIsPolling(false);
      if (pollIntervalRef.current) {
        window.clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  const startPolling = useCallback(
    (id: string) => {
      setWorkflowId(id);
      setIsLoading(true);
      setIsPolling(true);
      setError(null);

      // Immediate fetch
      fetchStatus(id);

      // Start 2s interval
      if (pollIntervalRef.current) {
        window.clearInterval(pollIntervalRef.current);
      }
      pollIntervalRef.current = window.setInterval(() => {
        fetchStatus(id);
      }, 2000);
    },
    [fetchStatus]
  );

  const stopPolling = useCallback(() => {
    setIsPolling(false);
    if (pollIntervalRef.current) {
      window.clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, []);

  const refetch = useCallback(async () => {
    if (workflowId) {
      setIsLoading(true);
      await fetchStatus(workflowId);
    }
  }, [workflowId, fetchStatus]);

  useEffect(() => {
    if (initialWorkflowId) {
      startPolling(initialWorkflowId);
    }
    return () => {
      if (pollIntervalRef.current) {
        window.clearInterval(pollIntervalRef.current);
      }
    };
  }, [initialWorkflowId, startPolling]);

  return {
    workflow,
    diagnostics,
    isLoading,
    isPolling,
    error,
    startPolling,
    stopPolling,
    refetch,
  };
}
