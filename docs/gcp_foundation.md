# PaperTrail AI — Google Cloud Architecture & Foundation

This document outlines the Google Cloud Infrastructure setup for **PaperTrail AI**, prepared for the **All Things Agentic Hackathon 2026**.

---

## 1. High-Level GCP Component Diagram

```text
                               Google Cloud Platform
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                                                                 │
│   ┌─────────────────────┐       ┌─────────────────────┐                         │
│   │   Cloud Run API     │       │ Artifact Registry   │                         │
│   │   (Compute Gateway) │       │ (Container Images)  │                         │
│   └──────────┬──────────┘       └─────────────────────┘                         │
│              │                                                                  │
│              ▼                                                                  │
│   ┌─────────────────────┐  Role  ┌──────────────────────────────────────────┐   │
│   │ papertrail-runtime  ├───────►│ Least Privilege IAM Permissions          │   │
│   │  (Service Account)  │        │ - Datastore User (Firestore)             │   │
│   └──────────┬──────────┘        │ - Storage Object Admin (GCS)             │   │
│              │                   │ - Pub/Sub Publisher/Subscriber           │   │
│              │                   │ - Secret Manager Secret Accessor         │   │
│              │                   └──────────────────────────────────────────┘   │
│              │                                                                  │
│     ┌────────┼───────────────────────────┬───────────────────────────┐          │
│     │        │                           │                           │          │
│     ▼        ▼                           ▼                           ▼          │
│  ┌──────┐ ┌───────────────────────┐ ┌─────────────────────────┐ ┌─────────────┐ │
│  │Firestore│ │ Cloud Storage Buckets │ │ Pub/Sub Topics/Subs     │ │ Secret Mgr  │ │
│  │Native│ │ - papertrail-documents│ │ - papertrail-events-top │ │ - Gemini Key│ │
│  │ DB   │ │ - papertrail-reports  │ │ - papertrail-events-sub │ │  (Secret)   │ │
│  └──────┘ └───────────────────────┘ └─────────────────────────┘ └─────────────┘ │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Required Google Cloud APIs

The following APIs are required and must be enabled on the target GCP project:

- `run.googleapis.com` (Cloud Run API)
- `firestore.googleapis.com` (Cloud Firestore API)
- `pubsub.googleapis.com` (Cloud Pub/Sub API)
- `storage.googleapis.com` (Cloud Storage API)
- `secretmanager.googleapis.com` (Secret Manager API)
- `artifactregistry.googleapis.com` (Artifact Registry API)
- `logging.googleapis.com` (Cloud Logging API)
- `monitoring.googleapis.com` (Cloud Monitoring API)

---

## 3. IAM & Runtime Identity

- **Dedicated Service Account**: `papertrail-runtime@<project_id>.iam.gserviceaccount.com`
- **Assigned IAM Roles**:
  - `roles/datastore.user` (Firestore read/write access)
  - `roles/storage.objectAdmin` (Cloud Storage document/report management)
  - `roles/pubsub.editor` (Pub/Sub topic publishing and message subscription)
  - `roles/secretmanager.secretAccessor` (Secret Manager payload retrieval)
  - `roles/logging.logWriter` (Cloud Logging emission)

---

## 4. Resource Definitions & Naming Conventions

### Firestore Native Database
- Database ID: `(default)`
- Location: `us-central1`

### Cloud Storage Buckets
- Documents Bucket: `papertrail-ai-documents-dev` (Private, uniform bucket-level access)
- Reports Bucket: `papertrail-ai-reports-dev` (Private, uniform bucket-level access)

### Pub/Sub Topics & Subscriptions
- Event Topic: `papertrail-events-topic`
- Event Subscription: `papertrail-events-sub`

### Secret Manager Secrets
- Gemini API Key Secret: `papertrail-gemini-api-key`

---

## 5. Local Development vs. Production Cloud Authentication

- **Local Development**:
  Developers authenticate using Application Default Credentials (ADC):
  ```bash
  gcloud auth application-default login
  ```
  If GCP credentials are not supplied locally, `app/core/gcp.py` gracefully degrades with non-blocking fallbacks.

- **Production Deployment (Cloud Run)**:
  Cloud Run automatically binds the `papertrail-runtime` service account identity without requiring hardcoded JSON service account keys in code or Git repositories.

---

## 6. Cost Optimization Principles
- **Scale to Zero**: Cloud Run services scale down to 0 instances when idle.
- **No Unused Always-On Resources**: Avoid GKE clusters or dedicated Cloud SQL instances.
