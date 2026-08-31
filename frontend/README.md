# PaperTrail AI — Enterprise Dashboard

Professional financial document intelligence, forensic fraud detection, compliance evaluation, and risk dashboard for PaperTrail AI.

## Architecture

- **Framework**: React 19 + TypeScript + Vite
- **Design System**: Enterprise Financial Compliance Aesthetic (Dense, Evidence-First, Zero-Distraction)
- **State Management**: Real-time polling over native PaperTrail FastAPI endpoints (`/documents`, `/api/v1/pipeline/*`, `/health`, `/health/ready`, `/metrics`)
- **Security**: Strict CORS binding via `FRONTEND_ORIGIN` (no wildcards), zero client-side secret exposure, authenticated reviewer principal headers

## Development

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Production build
npm run build
```

## Available Pages

1. **Overview**: Executive KPI overview, active cloud provider readiness, recent analysis workflows session table.
2. **Documents / Intelligence**: Drag-and-drop file upload with client-side SHA-256 preview and authoritative backend storage registration.
3. **Analysis Pipeline**: Real-time stage progression tracker displaying deterministic monotonic revision locking, status reasons, and diagnostics.
4. **Forensic Findings**: Table of 8 deterministic forensic rules with observed vs expected evidence and severity badges.
5. **Compliance (POL-FIN-001)**: Organizational policy control mapping and verification status.
6. **Risk Center**: Multi-dimensional risk scoring model across 5 weighted dimensions with autonomous routing decisions.
7. **Human Review Workbench**: Authenticated auditor queue for reviewing and resuming escalated workflows.
8. **Cryptographic Audit Ledger**: Immutable SHA-256 linked event chain and Merkle sealing overview.
9. **Reports**: Evidence report summaries and raw document artifact downloads.
