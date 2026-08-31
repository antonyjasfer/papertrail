import { useCallback, useEffect, useState } from 'react';
import { apiClient } from '../services/apiClient';
import type { HealthResponse, ReadinessResponse } from '../types/api';

export interface SystemHealthState {
  health: HealthResponse | null;
  readiness: ReadinessResponse | null;
  metrics: Record<string, unknown> | null;
  isConnected: boolean;
  isLoading: boolean;
  error: string | null;
  lastChecked: Date | null;
}

export function useHealth(pollIntervalMs = 15000): SystemHealthState & { refresh: () => Promise<void> } {
  const [state, setState] = useState<SystemHealthState>({
    health: null,
    readiness: null,
    metrics: null,
    isConnected: false,
    isLoading: true,
    error: null,
    lastChecked: null,
  });

  const checkHealth = useCallback(async () => {
    try {
      const [health, readiness, metrics] = await Promise.all([
        apiClient.getHealth().catch(() => null),
        apiClient.getReadiness().catch(() => null),
        apiClient.getMetrics().catch(() => null),
      ]);

      const isConnected = !!health && health.status === 'ok';

      setState({
        health,
        readiness,
        metrics,
        isConnected,
        isLoading: false,
        error: isConnected ? null : 'Cannot reach PaperTrail API',
        lastChecked: new Date(),
      });
    } catch (err) {
      setState((prev) => ({
        ...prev,
        isConnected: false,
        isLoading: false,
        error: (err as Error).message || 'Health check failed',
        lastChecked: new Date(),
      }));
    }
  }, []);

  useEffect(() => {
    checkHealth();
    const interval = window.setInterval(checkHealth, pollIntervalMs);
    return () => window.clearInterval(interval);
  }, [checkHealth, pollIntervalMs]);

  return {
    ...state,
    refresh: checkHealth,
  };
}
