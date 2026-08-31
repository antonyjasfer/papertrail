# PaperTrail AI

**PaperTrail AI** is an enterprise-grade Autonomous Document Intelligence, Forensic Fraud Detection, Compliance Risk Evaluation, Cryptographic Provenance, and Deterministic Audit Report Generation Platform built for the **All Things Agentic Hackathon 2026**.

---

## Multi-Cloud Architecture & Hackathon Technology Stack

PaperTrail is engineered with a **provider-neutral multi-cloud architecture** using a dynamic dependency-injection factory layer (`app/infrastructure/factory.py`).

```text
                              ┌──────────────────────────────────┐
                              │         User / Client            │
                              └────────────────┬─────────────────┘
                                               │
                                               ▼
                              ┌──────────────────────────────────┐
                              │          FastAPI Gateway         │
                              └────────────────┬─────────────────┘
                                               │
                                               ▼
                              ┌──────────────────────────────────┐
                              │    Dynamic Provider Factory      │
                              └────────┬────────────────┬────────┘
                                       │                │
            PAPERTRAIL_CLOUD_PROVIDER  │                │  PAPERTRAIL_CLOUD_PROVIDER
                   = "azure"           │                │        = "gcp"
                                       ▼                ▼
                     ┌───────────────────────┐   ┌───────────────────────────┐
                     │   Azure Provider      │   │    Google Cloud Stack     │
                     │  ───────────────────  │   │   ─────────────────────   │
                     │ • Azure Container App │   │ • Cloud Run (Serverless)  │
                     │ • Azure Cosmos DB     │   │ • Gemini 3.5 Flash        │
                     │ • Azure Blob Storage  │   │ • Cloud Storage (GCS)     │
                     │ • Azure Service Bus   │   │ • Cloud Pub/Sub           │
                     │ • Azure Key Vault     │   │ • Cloud Firestore         │
                     │                       │   │ • Secret Manager          │
                     │ [Live Tested Backend] │   │ [Deployable / Supported]  │
                     └───────────────────────┘   └───────────────────────────┘
```

### Google Technologies & Agent Stack

1. **Gemini 3.5+**: Powered by `gemini-3.5-flash` for deterministic multimodal document extraction, classification, zero-hallucination validation, and prompt injection defense.
2. **Google Agent Framework / GenAI SDK**: Implemented using the official `google-genai` SDK (`genai.Client`) with structured Pydantic schema validation.
3. **Google Cloud Run**: Lean multi-stage container deployment (`Dockerfile`, `PORT=8080`, non-root user `appuser:10001`) with instant health and readiness verification.
4. **Google Cloud Provider Layer**:
   - **Cloud Firestore**: Atomic state persistence, monotonic revisions, execution claims, and outbox event storage (`FirestoreStateManager`, `WorkflowRepository`, `DocumentRepository`, `AuditEventRepository`).
   - **Cloud Storage (GCS)**: Raw document payload and audit report storage (`GCSStorageProvider`).
   - **Cloud Pub/Sub**: Asynchronous pipeline stage event dispatching (`PubSubPublisher`, `PubSubSubscriber`).
   - **Secret Manager**: Secure API key retrieval via Google Application Default Credentials (`GCPSecretManagerProvider`).

> [!NOTE]
> **Deployment Status**: Azure Container Apps serves as the primary live validated production deployment across all 7 rigorous test scenarios (Clean, Line-Item Arithmetic Mismatch, Duplicate Invoices, Structural Anomalies, Ambiguity Handling, False-Positive Validation, and Malformed Handling). The codebase includes a native, complete Google Cloud deployment path documented in [docs/deployment/google-cloud.md](docs/deployment/google-cloud.md).

---

## Core Pipeline Architecture

```text
HTTP Client
      │
      ▼
FastAPI Gateway
      │
      ▼
Document Storage Service (IStorageProvider: GCS / Azure Blob)
   │                       │
   ▼                       ▼
Object Storage        Document Repository (Firestore / Cosmos DB)
(Raw Artifacts)            │
                           ▼
              Document Intelligence Service
                           │
                           ▼
              Document Intelligence Agent
                           │
                           ▼
                 Gemini 3.5 Flash (google-genai SDK)
                           │
                           ▼
              Deterministic Python Validation
                           │
                           ▼
              Deterministic Forensic Engine
                           │
                           ▼
              Evidence-Backed Forensic Findings
                           │
                           ▼
              Deterministic Compliance Engine
                           │
                           ▼
              Evidence-Backed Compliance Findings
                           │
                           ▼
              Deterministic Risk Assessment Engine
                           │
                           ▼
              Auditable Multi-Dimensional Decimal Risk Assessment
                           │
                           ▼
              Cryptographic Audit & Provenance Layer
                           │
                           ▼
              Immutable SHA-256 Prev-Hash Audit Chain & Evidence Bundle
                           │
                           ▼
              Deterministic Audit Report Generation Layer
                           │
                           ▼
              Canonical Report JSON (content_hash) & ReportLab PDF (artifact_hash)
```

---

## Key Architectural Principles

1. **Deterministic State Machine**: Lifecycle transitions (`app/core/state.py`) are strictly governed by Python domain logic with monotonic revision locking.
2. **Provider-Neutral Dependency Injection**: Storage, databases, event brokers, and secrets resolve dynamically via `app/infrastructure/factory.py`.
3. **Cryptographic Checksum & Immutability**: Every document is fingerprinted using SHA-256, and all audit events form an immutable cryptographic hash chain.
4. **Zero-Hallucination AI Extraction**: Document Intelligence uses Gemini 3.5 Flash with strict factual fallback isolation—never fabricating vendor, invoice, or financial identifiers on API failure.
5. **Deterministic Python Domain Engines**: Forensics, Compliance, and Risk engines run 100% deterministic Python arithmetic with exact `Decimal` precision, strict clock isolation, and zero LLM hallucination risk.
6. **Container & Cloud Run Ready**: Complies with Google Cloud Run runtime contracts (fast startup, zero blocking network calls on module import, non-root security context).

---

## Technical Documentation

- [Google Cloud Deployment Guide](docs/deployment/google-cloud.md)
- [GCP Foundation Architecture](docs/gcp_foundation.md)
- [Core State Machine Specification](docs/state_machine.md)
- [Firestore Workflow Repository Documentation](docs/firestore_repository.md)
- [Document Storage Layer Documentation](docs/document_storage.md)
- [FastAPI Gateway Documentation](docs/fastapi_gateway.md)
- [Document Intelligence Agent Documentation](docs/document_intelligence_agent.md)
- [Deterministic Forensic Engine Documentation](docs/forensic_engine.md)
- [Deterministic Compliance Engine Documentation](docs/compliance_engine.md)
- [Deterministic Risk Assessment Engine Documentation](docs/risk_engine.md)
- [Cryptographic Audit & Provenance Documentation](docs/audit_provenance.md)
- [Deterministic Audit Report Generation Documentation](docs/report_generation.md)

---

## Running Verification Tests

Run the complete verification test suite (293 tests covering GCP provider hardening, Azure integration, forensics, compliance, risk, and report generation):

```bash
.\venv\Scripts\pytest -v
```
