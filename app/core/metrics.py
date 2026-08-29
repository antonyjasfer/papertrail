"""PaperTrail AI — Production Application Metrics Registry.

Provides thread-safe in-process metrics tracking (counters, gauges, duration summaries)
for API traffic, orchestration lifecycles, adapter executions, and cloud resource operations.
Exposes snapshots via JSON/Prometheus format.
"""

import threading
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional


class MetricsRegistry:
    """Thread-safe application metrics registry."""

    _instance: Optional["MetricsRegistry"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "MetricsRegistry":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(MetricsRegistry, cls).__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        self.lock = threading.RLock()
        self.counters: Dict[str, float] = defaultdict(float)
        self.gauges: Dict[str, float] = {}
        self.durations: Dict[str, List[float]] = defaultdict(list)
        self.last_updated: float = time.time()

    def increment(self, name: str, value: float = 1.0, tags: Optional[Dict[str, str]] = None) -> None:
        """Increment a counter metric."""
        metric_key = self._format_key(name, tags)
        with self.lock:
            self.counters[metric_key] += value
            self.last_updated = time.time()

    def set_gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Set a gauge metric value."""
        metric_key = self._format_key(name, tags)
        with self.lock:
            self.gauges[metric_key] = value
            self.last_updated = time.time()

    def record_duration(self, name: str, duration_seconds: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Record an execution duration observation."""
        metric_key = self._format_key(name, tags)
        with self.lock:
            samples = self.durations[metric_key]
            samples.append(round(duration_seconds, 4))
            if len(samples) > 500:  # Keep bounded rolling buffer
                self.durations[metric_key] = samples[-500:]
            self.last_updated = time.time()

    def _format_key(self, name: str, tags: Optional[Dict[str, str]]) -> str:
        if not tags:
            return name
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}{{{tag_str}}}"

    def get_snapshot(self) -> Dict[str, Any]:
        """Generate a complete point-in-time metrics snapshot."""
        with self.lock:
            duration_summaries = {}
            for k, samples in self.durations.items():
                if samples:
                    duration_summaries[k] = {
                        "count": len(samples),
                        "total_seconds": round(sum(samples), 4),
                        "min_seconds": round(min(samples), 4),
                        "max_seconds": round(max(samples), 4),
                        "avg_seconds": round(sum(samples) / len(samples), 4),
                        "p95_seconds": round(sorted(samples)[int(len(samples) * 0.95)], 4) if len(samples) >= 20 else round(max(samples), 4),
                    }

            return {
                "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.last_updated)),
                "counters": dict(self.counters),
                "gauges": dict(self.gauges),
                "durations": duration_summaries,
            }

    def reset_for_test(self) -> None:
        """Reset all metrics (test helper)."""
        with self.lock:
            self.counters.clear()
            self.gauges.clear()
            self.durations.clear()
            self.last_updated = time.time()


# Global singleton
metrics = MetricsRegistry()


# Convenience recording functions
def record_workflow_start(workflow_id: str) -> None:
    metrics.increment("workflow_started_total")


def record_workflow_complete(workflow_id: str, duration_seconds: Optional[float] = None) -> None:
    metrics.increment("workflow_completed_total")
    if duration_seconds is not None:
        metrics.record_duration("workflow_duration_seconds", duration_seconds)


def record_workflow_failed(workflow_id: str, reason: Optional[str] = None) -> None:
    metrics.increment("workflow_failed_total")


def record_workflow_escalated(workflow_id: str) -> None:
    metrics.increment("workflow_escalated_total")


def record_adapter_execution(adapter_name: str, duration_seconds: float, success: bool) -> None:
    tags = {"adapter": adapter_name}
    metrics.record_duration("adapter_execution_duration_seconds", duration_seconds, tags)
    if not success:
        metrics.increment("adapter_failure_total", tags=tags)


def record_claim_conflict(workflow_id: str) -> None:
    metrics.increment("claim_conflict_total")


def record_idempotency_duplicate(workflow_id: str) -> None:
    metrics.increment("idempotency_duplicate_total")


def record_retry(component: str, reason: Optional[str] = None) -> None:
    metrics.increment("retry_total", tags={"component": component})


def record_report_generation(success: bool, duration_seconds: Optional[float] = None) -> None:
    metrics.increment("report_generation_total")
    if not success:
        metrics.increment("report_generation_failure_total")
    if duration_seconds is not None:
        metrics.record_duration("report_generation_duration_seconds", duration_seconds)


def record_audit_seal(success: bool) -> None:
    if success:
        metrics.increment("audit_seal_success_total")
    else:
        metrics.increment("audit_seal_failure_total")


def record_api_request(endpoint: str, method: str, status_code: int, duration_seconds: float) -> None:
    tags = {"endpoint": endpoint, "method": method, "status": str(status_code)}
    metrics.increment("api_requests_total", tags=tags)
    metrics.record_duration("api_request_duration_seconds", duration_seconds, tags={"endpoint": endpoint, "method": method})
    if status_code >= 400:
        metrics.increment("api_errors_total", tags={"endpoint": endpoint, "status": str(status_code)})
