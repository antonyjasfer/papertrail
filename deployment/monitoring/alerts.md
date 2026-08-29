# PaperTrail AI — Phase 17 Operational Alerting Specification

This document details the production alert rules configured or specified for the PaperTrail AI deployment on Azure Container Apps, Azure Service Bus, Cosmos DB, and Azure Blob Storage.

---

## 1. Alert Summary Matrix

| Alert Name | Target Resource | Trigger Condition | Severity | Eval Window | Action | Status |
|---|---|---|---|---|---|---|
| **API_Unhealthy** | `papertrail-api` | Failed probes or 5xx error rate > 5% over 5m | Sev 1 (Critical) | 5m | Page SRE | **CONFIGURED** |
| **Worker_Unhealthy** | `papertrail-worker` | Replicas = 0 with Active Messages > 0 | Sev 1 (Critical) | 5m | Page SRE | **CONFIGURED** |
| **ServiceBus_DeadLetter_Threshold** | `papertrail-sb-dev-2026` | Dead-letter messages > 0 in topic subscription | Sev 2 (High) | 5m | Email On-Call | **CONFIGURED** |
| **Repeated_Workflow_Failures** | Log Analytics | Workflow failures >= 3 in 15m window | Sev 2 (High) | 15m | Email On-Call | **CONFIGURED** |
| **Stuck_Workflow_Detected** | Log Analytics | Workflow non-terminal for > 300s | Sev 3 (Warning) | 10m | Ticket Creation | **CONFIGURED** |
| **CosmosDB_Throttling_429** | `papertrailcosmosdev2026` | HTTP 429 RequestRateTooLarge > 10 in 5m | Sev 2 (High) | 5m | Auto-scale RU / Alert | **CONFIGURED** |
| **Report_Generation_Failure** | Log Analytics | `outcome == 'FAILED'` in `report_adapter` | Sev 3 (Warning) | 15m | Email On-Call | **CONFIGURED** |
| **Audit_Seal_Failure** | Log Analytics | `outcome == 'FAILED'` in `audit_adapter` | Sev 1 (Critical) | 5m | Page Security Lead | **CONFIGURED** |

---

## 2. Detailed Alert Rules & KQL Logic

### Alert 1: API Error Rate Spike (Sev 1)
```kql
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(5m)
| where ContainerAppName_s == "papertrail-api"
| extend LogData = parse_json(Log_s)
| where LogData.component == "api" and isnotempty(LogData.http_status)
| summarize
    Total = count(),
    Errors = countif(toint(LogData.http_status) >= 500)
| extend ErrorRate = (todouble(Errors) / todouble(Total)) * 100.0
| where ErrorRate > 5.0 and Total >= 10
```

### Alert 2: Worker Dead-Letter Ingestion (Sev 2)
```kql
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(5m)
| where ContainerAppName_s == "papertrail-worker"
| extend LogData = parse_json(Log_s)
| where LogData.operation == "message_deadlettered" or LogData.outcome == "DEADLETTERED"
| summarize DeadLetterCount = count()
| where DeadLetterCount > 0
```

### Alert 3: Stuck Workflow Threshold (> 300s in non-terminal state) (Sev 3)
```kql
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(1h)
| extend LogData = parse_json(Log_s)
| where isnotempty(LogData.workflow_id) and LogData.operation in ("start_workflow", "state_transition")
| summarize
    StartTime = min(TimeGenerated),
    LastEventTime = max(TimeGenerated),
    LatestState = take_anyif(tostring(LogData.target_state), isnotempty(LogData.target_state))
    by WorkflowId = tostring(LogData.workflow_id)
| where LatestState !in ("COMPLETED", "FAILED", "ESCALATED", "REQUIRES_REVIEW")
| extend InactiveSec = datetime_diff('second', now(), LastEventTime)
| where InactiveSec > 300
```

### Alert 4: Cryptographic Audit Sealing Failure (Sev 1)
```kql
ContainerAppConsoleLogs_CL
| where TimeGenerated > ago(5m)
| extend LogData = parse_json(Log_s)
| where LogData.component == "audit_adapter" and (LogData.outcome == "FAILED" or LogData.error_category == "AUDIT_ERROR")
| summarize FailureCount = count()
| where FailureCount > 0
```

---

## 3. Operational Runbooks

### Runbook for `ServiceBus_DeadLetter_Threshold`
1. Inspect dead-letter messages using Azure Service Bus Explorer or CLI:
   `az servicebus topic subscription show --resource-group papertrail-azure-dev --namespace-name papertrail-sb-dev-2026 --topic-name papertrail-workflow-events --name papertrail-orchestrator-sub`
2. Run KQL query 3 (`ContainerAppConsoleLogs_CL | where LogData.operation == 'message_deadlettered'`) to retrieve the `workflow_id`, `delivery_count`, and `error_details`.
3. Check Cosmos DB workflow state for the associated `workflow_id`.
4. Resubmit or replay dead-letter messages after rectifying the root cause.
