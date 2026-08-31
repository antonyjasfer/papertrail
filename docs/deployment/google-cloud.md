# PaperTrail AI — Google Cloud Deployment Guide

This document provides complete instructions for deploying and running PaperTrail AI on Google Cloud infrastructure.

---

## 1. Overview & Architecture

PaperTrail is designed with a provider-neutral architecture using dependency-injection factories (`app/infrastructure/factory.py`). While Azure Container Apps hosts the primary validated production deployment, the codebase contains a native **Google Cloud provider stack**:

```
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
                              │         Provider Factory         │
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

---

## 2. Google Cloud Services Used

| Service | Component / Role | Runtime Implementation |
| :--- | :--- | :--- |
| **Google Cloud Run** | Primary Serverless Container Runtime | `Dockerfile` (Port 8080, non-root user `appuser:10001`) |
| **Google GenAI SDK** | Multimodal Document Extraction | `google-genai` with `gemini-3.5-flash` (`DocumentIntelligenceAgent`) |
| **Cloud Firestore** | Document Metadata, Workflow State, Audit Log | `FirestoreStateManager`, `WorkflowRepository`, `DocumentRepository` |
| **Cloud Storage (GCS)** | Raw PDF Invoices & Generated Audit Reports | `GCSStorageProvider` |
| **Cloud Pub/Sub** | Asynchronous Workflow Event Messaging | `PubSubPublisher`, `PubSubSubscriber` |
| **Secret Manager** | Secure Gemini API Key Storage & Access | `GCPSecretManagerProvider` |

---

## 3. Prerequisites

1. **Google Cloud SDK (`gcloud`)**: Installed and authenticated.
   ```bash
   gcloud auth login
   gcloud auth application-default login
   ```
2. **GCP Project Configuration**:
   ```bash
   export GCP_PROJECT_ID="your-gcp-project-id"
   export GCP_REGION="us-central1"
   gcloud config set project $GCP_PROJECT_ID
   ```
3. **Enable Required Google Cloud APIs**:
   ```bash
   gcloud services enable \
     run.googleapis.com \
     artifactregistry.googleapis.com \
     cloudbuild.googleapis.com \
     secretmanager.googleapis.com \
     firestore.googleapis.com \
     storage.googleapis.com \
     pubsub.googleapis.com
   ```

---

## 4. Secret Manager Configuration

Store the Gemini API key in Google Cloud Secret Manager:

```bash
# Create secret in Secret Manager
echo -n "<YOUR_GEMINI_API_KEY>" | gcloud secrets create papertrail-gemini-api-key \
  --data-file=- \
  --replication-policy="automatic"
```

---

## 5. Google Cloud Run Deployment

Deploy PaperTrail API directly from source using Google Cloud Build and Cloud Run:

```bash
gcloud run deploy papertrail-api \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --port 8080 \
  --set-env-vars "PAPERTRAIL_CLOUD_PROVIDER=gcp,ENVIRONMENT=production,GCP_PROJECT_ID=${GCP_PROJECT_ID},GCP_REGION=us-central1,GEMINI_MODEL=gemini-3.5-flash" \
  --set-secrets "GEMINI_API_KEY=papertrail-gemini-api-key:latest"
```

---

## 6. Verifying the Deployment

### 6.1 Basic Health Check
```bash
curl -i "https://<cloud-run-service-url>/health"
```
**Expected Response:**
```json
{
  "status": "ok",
  "service": "PaperTrail AI",
  "version": "0.1.0",
  "phase": "17"
}
```

### 6.2 Cloud Provider Readiness Check
```bash
curl -i "https://<cloud-run-service-url>/health/ready"
```
**Expected Response:**
```json
{
  "status": "ready",
  "service": "PaperTrail AI",
  "provider": "gcp",
  "environment": "production",
  "dependencies": {
    "firestore": "configured",
    "cloud_storage": "configured",
    "pubsub": "configured"
  }
}
```

### 6.3 Document Intelligence Analysis
```bash
curl -X POST "https://<cloud-run-service-url>/documents" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@PaperTrail_Test_Documents/01_clean/clean_invoice_739.pdf"
```

---

## 7. Running Locally in GCP Mode

To run PaperTrail locally with GCP provider active:

```bash
# Set environment variables
export PAPERTRAIL_CLOUD_PROVIDER=gcp
export ENVIRONMENT=development
export GCP_PROJECT_ID="your-gcp-project-id"
export GEMINI_MODEL="gemini-3.5-flash"
export GEMINI_API_KEY="<YOUR_GEMINI_API_KEY>"

# Start uvicorn server
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

---

## 8. Multi-Cloud & Regression Notes

* **Azure Production Backend**: Azure Container Apps, Cosmos DB, Azure Blob, and Service Bus remain the primary 7-stage verified production deployment.
* **Provider Independence**: Switching between providers requires zero code changes—only setting `PAPERTRAIL_CLOUD_PROVIDER=gcp` or `PAPERTRAIL_CLOUD_PROVIDER=azure`.
