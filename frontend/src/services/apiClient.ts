import type {
  DocumentResponse,
  HealthResponse,
  ReadinessResponse,
  StartPipelineRequest,
  WorkflowDiagnostics,
  WorkflowStatus,
} from '../types/api';

const DEFAULT_PROD_API = 'https://papertrail-api.gentlesmoke-4100f438.centralindia.azurecontainerapps.io';
const DEFAULT_DEV_API = 'http://127.0.0.1:8080';

const API_BASE =
  import.meta.env.VITE_API_BASE_URL ||
  import.meta.env.VITE_API_BASE ||
  (import.meta.env.PROD ? DEFAULT_PROD_API : DEFAULT_DEV_API);

export class ApiError extends Error {
  status: number;
  statusText: string;
  data: unknown;

  constructor(status: number, statusText: string, data: unknown) {
    super(
      `API Error ${status}: ${
        typeof data === 'object' && data && 'detail' in data
          ? (data as { detail: string }).detail
          : statusText
      }`
    );
    this.name = 'ApiError';
    this.status = status;
    this.statusText = statusText;
    this.data = data;
  }
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  try {
    const res = await fetch(url, {
      ...options,
      headers: {
        ...options.headers,
      },
    });

    if (!res.ok) {
      let errData: unknown;
      try {
        errData = await res.json();
      } catch {
        errData = await res.text();
      }
      throw new ApiError(res.status, res.statusText, errData);
    }

    if (res.status === 204) {
      return {} as T;
    }

    return await res.json();
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new Error(`Network failure connecting to PaperTrail backend (${url}): ${(error as Error).message}`);
  }
}

export const apiClient = {
  // Document endpoints
  async uploadDocument(file: File): Promise<DocumentResponse> {
    const formData = new FormData();
    formData.append('file', file);
    return request<DocumentResponse>('/documents', {
      method: 'POST',
      body: formData,
    });
  },

  async getDocument(documentId: string): Promise<DocumentResponse> {
    return request<DocumentResponse>(`/documents/${documentId}`);
  },

  async downloadDocument(documentId: string): Promise<Blob> {
    const url = `${API_BASE}/documents/${documentId}/download`;
    const res = await fetch(url);
    if (!res.ok) {
      throw new ApiError(res.status, res.statusText, await res.text());
    }
    return res.blob();
  },

  async deleteDocument(documentId: string): Promise<{ document_id: string; status: string; artifact_deleted: boolean; metadata_retained: boolean }> {
    return request(`/documents/${documentId}`, {
      method: 'DELETE',
    });
  },

  // Pipeline / Orchestration endpoints
  async startPipeline(req: StartPipelineRequest): Promise<WorkflowStatus> {
    return request<WorkflowStatus>('/api/v1/pipeline/start', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(req),
    });
  },

  async getPipelineStatus(workflowId: string): Promise<WorkflowStatus> {
    return request<WorkflowStatus>(`/api/v1/pipeline/${workflowId}/status`);
  },

  async resumePipeline(
    workflowId: string,
    payload: {
      reviewer_id: string;
      decision: 'APPROVED' | 'REJECTED' | 'RE_EVALUATE';
      decision_reason: string;
      requested_target: string;
    },
    reviewerPrincipal: string
  ): Promise<WorkflowStatus> {
    return request<WorkflowStatus>(`/api/v1/pipeline/${workflowId}/resume`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Reviewer-Principal': reviewerPrincipal,
      },
      body: JSON.stringify({
        payload: {
          workflow_id: workflowId,
          ...payload,
        },
      }),
    });
  },

  async getWorkflowDiagnostics(workflowId: string, thresholdSeconds = 300): Promise<WorkflowDiagnostics> {
    return request<WorkflowDiagnostics>(`/api/v1/pipeline/${workflowId}/diagnostics?threshold_seconds=${thresholdSeconds}`);
  },

  // System Observability & Health endpoints
  async getHealth(): Promise<HealthResponse> {
    return request<HealthResponse>('/health');
  },

  async getReadiness(): Promise<ReadinessResponse> {
    return request<ReadinessResponse>('/health/ready');
  },

  async getMetrics(): Promise<Record<string, unknown>> {
    return request<Record<string, unknown>>('/metrics');
  },
};
