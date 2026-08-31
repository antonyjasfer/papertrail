import React from 'react';

interface StatusBadgeProps {
  status: string;
  type?: 'state' | 'severity' | 'health' | 'risk';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, type = 'state' }) => {
  let badgeClass = 'badge-neutral';
  let displayStatus = status;

  if (type === 'state') {
    switch (status) {
      case 'COMPLETED':
        badgeClass = 'badge-success';
        break;
      case 'REQUIRES_REVIEW':
        badgeClass = 'badge-warning';
        break;
      case 'FAILED':
      case 'ESCALATED':
        badgeClass = 'badge-error';
        break;
      case 'INGESTING':
      case 'EXTRACTING':
      case 'EXTRACTED':
      case 'FORENSIC_ANALYSIS':
      case 'COMPLIANCE_ANALYSIS':
      case 'RISK_ASSESSED':
      case 'AUDIT_SEALED':
      case 'REPORT_GENERATED':
        badgeClass = 'badge-info';
        break;
      case 'UPLOADED':
      case 'STORED':
        badgeClass = 'badge-neutral';
        break;
      default:
        badgeClass = 'badge-neutral';
    }
  } else if (type === 'severity') {
    switch (status.toUpperCase()) {
      case 'CRITICAL':
        badgeClass = 'badge-critical';
        break;
      case 'HIGH':
        badgeClass = 'badge-high';
        break;
      case 'MEDIUM':
        badgeClass = 'badge-medium';
        break;
      case 'LOW':
        badgeClass = 'badge-low';
        break;
      default:
        badgeClass = 'badge-neutral';
    }
  } else if (type === 'health') {
    switch (status.toLowerCase()) {
      case 'ready':
      case 'configured':
      case 'ok':
        badgeClass = 'badge-success';
        break;
      case 'unconfigured':
      case 'degraded':
        badgeClass = 'badge-warning';
        break;
      case 'failed':
      case 'error':
        badgeClass = 'badge-error';
        break;
      default:
        badgeClass = 'badge-neutral';
    }
  } else if (type === 'risk') {
    switch (status.toUpperCase()) {
      case 'LOW':
        badgeClass = 'badge-success';
        break;
      case 'MEDIUM':
        badgeClass = 'badge-warning';
        break;
      case 'HIGH':
        badgeClass = 'badge-high';
        break;
      case 'CRITICAL':
        badgeClass = 'badge-critical';
        break;
      default:
        badgeClass = 'badge-neutral';
    }
  }

  return <span className={`badge ${badgeClass}`}>{displayStatus}</span>;
};
