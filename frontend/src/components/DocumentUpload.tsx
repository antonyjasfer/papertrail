import React, { useCallback, useState } from 'react';
import { apiClient } from '../services/apiClient';
import type { DocumentResponse, WorkflowStatus } from '../types/api';
import { calculateSHA256, formatBytes, formatDate } from '../utils/format';
import { StatusBadge } from './StatusBadge';

interface DocumentUploadProps {
  onWorkflowStarted: (workflow: WorkflowStatus, document: DocumentResponse) => void;
}

export const DocumentUpload: React.FC<DocumentUploadProps> = ({ onWorkflowStarted }) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [clientChecksum, setClientChecksum] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [isStartingPipeline, setIsStartingPipeline] = useState<boolean>(false);
  const [uploadedDoc, setUploadedDoc] = useState<DocumentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFileChange = useCallback(async (file: File) => {
    setSelectedFile(file);
    setError(null);
    setUploadedDoc(null);
    try {
      const sha = await calculateSHA256(file);
      setClientChecksum(sha);
    } catch {
      setClientChecksum(null);
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleFileChange(e.dataTransfer.files[0]);
      }
    },
    [handleFileChange]
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleUpload = async () => {
    if (!selectedFile) return;
    setIsUploading(true);
    setError(null);
    try {
      const doc = await apiClient.uploadDocument(selectedFile);
      setUploadedDoc(doc);
    } catch (err) {
      setError((err as Error).message || 'Failed to upload document');
    } finally {
      setIsUploading(false);
    }
  };

  const handleStartAnalysis = async () => {
    if (!uploadedDoc) return;
    setIsStartingPipeline(true);
    setError(null);
    try {
      const wf = await apiClient.startPipeline({
        document_id: uploadedDoc.document_id,
      });
      onWorkflowStarted(wf, uploadedDoc);
    } catch (err) {
      setError((err as Error).message || 'Failed to start analysis pipeline');
    } finally {
      setIsStartingPipeline(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>
      {/* Upload Zone */}
      <div className="card">
        <div className="card-header">
          <h3>Upload Financial Document</h3>
          <span style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)' }}>
            Max: 25 MB · PDF, PNG, JPEG, TXT
          </span>
        </div>
        <div className="card-body">
          <div
            className={`upload-zone ${isDragging ? 'drag-active' : ''}`}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onClick={() => document.getElementById('file-upload-input')?.click()}
          >
            <input
              type="file"
              id="file-upload-input"
              style={{ display: 'none' }}
              accept=".pdf,.png,.jpg,.jpeg,.txt,application/pdf,image/*,text/plain"
              onChange={(e) => {
                if (e.target.files && e.target.files.length > 0) {
                  handleFileChange(e.target.files[0]);
                }
              }}
            />
            <div className="upload-icon">📄</div>
            <div className="upload-title">
              {selectedFile ? selectedFile.name : 'Select or Drag & Drop Document'}
            </div>
            <div className="upload-sub">
              {selectedFile
                ? `${formatBytes(selectedFile.size)} · ${selectedFile.type || 'application/octet-stream'}`
                : 'Supports invoices, purchase orders, statements, receipts'}
            </div>
          </div>

          {/* Selected File Details */}
          {selectedFile && (
            <div
              style={{
                marginTop: 'var(--space-md)',
                padding: 'var(--space-md)',
                background: 'var(--color-bg-card-alt)',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--color-border)',
              }}
            >
              <div className="detail-grid">
                <div className="detail-item">
                  <span className="detail-label">Selected File</span>
                  <span className="detail-value">{selectedFile.name}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">File Size</span>
                  <span className="detail-value">{formatBytes(selectedFile.size)}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">MIME Type</span>
                  <span className="detail-value">{selectedFile.type || 'application/octet-stream'}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Client SHA-256</span>
                  <span className="detail-value mono" style={{ fontSize: '0.75rem' }}>
                    {clientChecksum || 'Computing...'}
                  </span>
                </div>
              </div>

              {!uploadedDoc && (
                <div style={{ marginTop: 'var(--space-md)', display: 'flex', gap: '8px' }}>
                  <button
                    className="btn btn-primary"
                    onClick={handleUpload}
                    disabled={isUploading}
                  >
                    {isUploading ? (
                      <>
                        <span className="loading-spinner" /> Uploading to Storage...
                      </>
                    ) : (
                      'Upload & Register Document'
                    )}
                  </button>
                  <button
                    className="btn btn-secondary"
                    onClick={() => {
                      setSelectedFile(null);
                      setClientChecksum(null);
                      setUploadedDoc(null);
                      setError(null);
                    }}
                    disabled={isUploading}
                  >
                    Clear
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Error notice */}
          {error && (
            <div
              style={{
                marginTop: 'var(--space-md)',
                padding: 'var(--space-md)',
                background: 'var(--color-error-bg)',
                border: '1px solid #fecaca',
                borderRadius: 'var(--radius-md)',
                color: 'var(--color-error)',
                fontSize: '0.85rem',
              }}
            >
              <strong>Error:</strong> {error}
            </div>
          )}
        </div>
      </div>

      {/* Uploaded Document Metadata (from backend) */}
      {uploadedDoc && (
        <div className="card">
          <div className="card-header">
            <h3>Registered Document Record (Authoritative Backend State)</h3>
            <StatusBadge status={uploadedDoc.status} type="state" />
          </div>
          <div className="card-body">
            <div className="detail-grid">
              <div className="detail-item">
                <span className="detail-label">Document ID</span>
                <span className="detail-value mono">{uploadedDoc.document_id}</span>
              </div>
              <div className="detail-item">
                <span className="detail-label">Authoritative Checksum</span>
                <span className="detail-value mono" style={{ fontSize: '0.75rem' }}>
                  {uploadedDoc.checksum}
                </span>
              </div>
              <div className="detail-item">
                <span className="detail-label">Storage Status</span>
                <span className="detail-value">{uploadedDoc.status}</span>
              </div>
              <div className="detail-item">
                <span className="detail-label">Created At</span>
                <span className="detail-value">{formatDate(uploadedDoc.created_at)}</span>
              </div>
            </div>

            <div
              style={{
                marginTop: 'var(--space-lg)',
                paddingTop: 'var(--space-md)',
                borderTop: '1px solid var(--color-border)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div>
                <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>
                  Ready for Autonomous Analysis
                </div>
                <div style={{ fontSize: '0.78rem', color: 'var(--color-text-secondary)' }}>
                  Triggers document intelligence, forensics, compliance, risk assessment, and audit sealing.
                </div>
              </div>

              <button
                className="btn btn-primary btn-lg"
                onClick={handleStartAnalysis}
                disabled={isStartingPipeline}
              >
                {isStartingPipeline ? (
                  <>
                    <span className="loading-spinner" /> Starting Pipeline...
                  </>
                ) : (
                  'Start Analysis'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
