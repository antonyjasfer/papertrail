# PaperTrail AI — Microsoft Azure Multi-Cloud Architecture

This document provides architectural reference, operational configuration, and deployment guidelines for PaperTrail AI running on Microsoft Azure.

---

## 1. Overview

PaperTrail AI operates with a **provider-neutral core** supporting both Google Cloud Platform (GCP) and Microsoft Azure concurrently.

| Capability | Google Cloud (Target / Prod) | Microsoft Azure (Additive Provider) |
| :--- | :--- | :--- |
| **NoSQL Database** | Cloud Firestore | Azure Cosmos DB for NoSQL |
| **Object Storage** | Cloud Storage (GCS) | Azure Blob Storage |
| **Event Messaging** | Cloud Pub/Sub | Azure Service Bus (Standard Tier) |
| **Secrets Management** | Secret Manager | Azure Key Vault |
| **Compute / Hosting** | Cloud Run | Azure Container Apps |
| **Identity & IAM** | Service Accounts / ADC | Managed Identity (`ManagedIdentityCredential`) |
| **AI Intelligence** | Google Gemini (`gemini-3.5-flash`) | Google Gemini (`gemini-3.5-flash`) |

---

## 2. Cosmos DB Transactional Architecture

Azure Cosmos DB transactional batch atomicity is bounded to a single container and partition key (`/workflow_id`). To achieve transaction parity with Firestore, all mutable workflow entities are co-located in the `workflow_state` container:

- `Item Type: WORKFLOW` (`id = "wf:{workflow_id}"`)
- `Item Type: OUTBOX` (`id = "outbox:{outbox_id}"`)
- `Item Type: EXECUTION_CLAIM` (`id = "claim:{logical_event_key_hash}"`)
- `Item Type: IDEMPOTENCY` (`id = "idemp:{logical_event_key_hash}"`)

Document metadata (`documents` container, partition `/document_id`) and immutable audit logs (`audit_events` container, partition `/workflow_id`) are maintained in separate containers.

---

## 3. Configuration & Runtime Provider Selection

Configure provider selection via environment variables:

```env
# Multi-Cloud Mode Selection
PAPERTRAIL_CLOUD_PROVIDER=azure          # 'gcp' | 'azure' | 'mock'

# Azure Service Endpoints
AZURE_COSMOS_ENDPOINT=https://papertrail-cosmos-dev.documents.azure.com:443/
AZURE_COSMOS_DATABASE=papertrail-db
AZURE_STORAGE_ACCOUNT_URL=https://papertrailstoragedev.blob.core.windows.net/
AZURE_SERVICEBUS_NAMESPACE=papertrail-sb-dev.servicebus.windows.net
AZURE_KEYVAULT_URL=https://papertrail-kv-dev.vault.azure.net/
```

---

## 4. Cost Model & Budget Safety (Planning Estimates)

Development workload estimated cost range under **Azure for Students ($100 credit)**:
- **Estimated Listed Range**: **$15.55 – $25.05 / month**
- **Budget Alert**: Configured at $25.00/month threshold.
- **Scale-to-Zero**: Container Apps set to `minReplicas = 0`.
- **Teardown**: Single-click script `deployment/azure/scripts/teardown.sh`.
