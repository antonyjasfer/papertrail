// ── PaperTrail AI — TypeScript API Types ──
// Matches actual backend response schemas. No invented fields.

export interface DocumentResponse {
  document_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
  updated_at: string;
  status: string;
  checksum: string;
}

export interface WorkflowStatus {
  workflow_id: string;
  document_id: string;
  current_state: string;
  workflow_revision: number;
  created_at: string;
  updated_at: string;
  failure_reason: string | null;
  escalation_reason: string | null;
  review_reason: string | null;
}

export interface WorkflowDiagnostics {
  workflow_id: string;
  document_id: string;
  current_state: string;
  workflow_revision: number;
  is_stuck: boolean;
  diagnostic_report: Record<string, unknown> | null;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  phase: string;
}

export interface ReadinessResponse {
  status: string;
  service: string;
  provider: string;
  environment: string;
  dependencies: Record<string, string>;
}

export interface MetricsResponse {
  [key: string]: unknown;
}

export interface StartPipelineRequest {
  document_id: string;
  workflow_id?: string;
}

// Known workflow states from the backend state machine
export const WORKFLOW_STATES = [
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
  'FAILED',
  'ESCALATED',
  'REQUIRES_REVIEW',
] as const;

export type WorkflowState = typeof WORKFLOW_STATES[number];

export const TERMINAL_STATES: WorkflowState[] = ['COMPLETED', 'FAILED', 'ESCALATED'];

export const REVIEW_STATES: WorkflowState[] = ['REQUIRES_REVIEW'];

// Pipeline stage mapping for display
export interface PipelineStage {
  key: string;
  label: string;
  statesCompleted: WorkflowState[];
  stateActive: WorkflowState;
}

export const PIPELINE_STAGES: PipelineStage[] = [
  { key: 'upload', label: 'Document Upload', statesCompleted: [], stateActive: 'UPLOADED' },
  { key: 'ingest', label: 'Ingestion', statesCompleted: ['UPLOADED'], stateActive: 'INGESTING' },
  { key: 'extract', label: 'Gemini Extraction', statesCompleted: ['UPLOADED', 'INGESTING'], stateActive: 'EXTRACTING' },
  { key: 'classify', label: 'Classification', statesCompleted: ['UPLOADED', 'INGESTING', 'EXTRACTING'], stateActive: 'EXTRACTED' },
  { key: 'forensics', label: 'Forensic Analysis', statesCompleted: ['UPLOADED', 'INGESTING', 'EXTRACTING', 'EXTRACTED'], stateActive: 'FORENSIC_ANALYSIS' },
  { key: 'compliance', label: 'Compliance Evaluation', statesCompleted: ['UPLOADED', 'INGESTING', 'EXTRACTING', 'EXTRACTED', 'FORENSIC_ANALYSIS'], stateActive: 'COMPLIANCE_ANALYSIS' },
  { key: 'risk', label: 'Risk Assessment', statesCompleted: ['UPLOADED', 'INGESTING', 'EXTRACTING', 'EXTRACTED', 'FORENSIC_ANALYSIS', 'COMPLIANCE_ANALYSIS'], stateActive: 'RISK_ASSESSED' },
  { key: 'audit', label: 'Cryptographic Audit', statesCompleted: ['UPLOADED', 'INGESTING', 'EXTRACTING', 'EXTRACTED', 'FORENSIC_ANALYSIS', 'COMPLIANCE_ANALYSIS', 'RISK_ASSESSED'], stateActive: 'AUDIT_SEALED' },
  { key: 'report', label: 'Evidence Report', statesCompleted: ['UPLOADED', 'INGESTING', 'EXTRACTING', 'EXTRACTED', 'FORENSIC_ANALYSIS', 'COMPLIANCE_ANALYSIS', 'RISK_ASSESSED', 'AUDIT_SEALED'], stateActive: 'REPORT_GENERATED' },
  { key: 'complete', label: 'Complete', statesCompleted: ['UPLOADED', 'INGESTING', 'EXTRACTING', 'EXTRACTED', 'FORENSIC_ANALYSIS', 'COMPLIANCE_ANALYSIS', 'RISK_ASSESSED', 'AUDIT_SEALED', 'REPORT_GENERATED'], stateActive: 'COMPLETED' },
];
