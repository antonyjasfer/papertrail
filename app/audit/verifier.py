import hashlib
import logging
from typing import Any, List, Optional, Set

from app.audit.constants import (
    AUDIT_SCHEMA_VERSION,
    EXPECTED_AUDIT_EVENT_SEQUENCE,
    GENESIS_PREVIOUS_HASH,
    HASH_ALGORITHM,
)
from app.audit.hashing import compute_event_hash, compute_hash, compute_payload_hash
from app.audit.models import (
    AnalysisEvidenceBundle,
    AuditEvent,
    AuditEventType,
    DocumentChecksumVerification,
    VerificationResult,
    VerificationStatus,
)

logger = logging.getLogger("papertrail.audit.verifier")


class AuditVerificationService:
    """Side-effect-free, deterministic audit chain verification engine."""

    def verify_event(self, event: AuditEvent) -> VerificationResult:
        """Verify self-integrity of a single AuditEvent."""
        if event.schema_version != AUDIT_SCHEMA_VERSION:
            return VerificationResult(
                status=VerificationStatus.INVALID,
                chain_length=1,
                verified_events=0,
                broken_at_event_id=event.event_id,
                failure_reason=f"Unsupported schema version '{event.schema_version}'.",
            )

        if event.provenance.hash_algorithm != HASH_ALGORITHM:
            return VerificationResult(
                status=VerificationStatus.INVALID,
                chain_length=1,
                verified_events=0,
                broken_at_event_id=event.event_id,
                failure_reason=f"Unsupported hash algorithm '{event.provenance.hash_algorithm}'.",
            )

        computed_hash = compute_event_hash(event)
        if computed_hash != event.event_hash:
            return VerificationResult(
                status=VerificationStatus.INVALID,
                chain_length=1,
                verified_events=0,
                broken_at_event_id=event.event_id,
                expected_hash=computed_hash,
                observed_hash=event.event_hash,
                failure_reason=f"Event self-hash mismatch for event '{event.event_id}'.",
            )

        return VerificationResult(
            status=VerificationStatus.VALID,
            chain_length=1,
            verified_events=1,
        )

    def verify_payload(self, event: AuditEvent, payload: Any) -> VerificationResult:
        """Verify that a payload's canonical hash matches event.payload_hash."""
        computed_payload_hash = compute_payload_hash(payload)
        if computed_payload_hash != event.payload_hash:
            return VerificationResult(
                status=VerificationStatus.INVALID,
                chain_length=1,
                verified_events=0,
                broken_at_event_id=event.event_id,
                expected_hash=computed_payload_hash,
                observed_hash=event.payload_hash,
                failure_reason=f"Payload hash mismatch for event '{event.event_id}'.",
            )
        return self.verify_event(event)

    def verify_chain(
        self,
        events: List[AuditEvent],
        document_bytes: Optional[bytes] = None,
    ) -> VerificationResult:
        """Verify a complete audit chain against cryptographic linkage and sequence completeness."""
        if not events:
            return VerificationResult(
                status=VerificationStatus.INVALID,
                chain_length=0,
                verified_events=0,
                failure_reason="Audit chain is empty.",
            )

        # Step 1: Linkage Traversal (Graph prev-hash linkage)
        # Build map of previous_event_hash -> event for linear traversal
        prev_map = {e.previous_event_hash: e for e in events}
        
        # Locate genesis event
        if GENESIS_PREVIOUS_HASH not in prev_map:
            return VerificationResult(
                status=VerificationStatus.INVALID,
                chain_length=len(events),
                verified_events=0,
                failure_reason=f"Genesis event with previous hash '{GENESIS_PREVIOUS_HASH}' was not found in chain.",
            )

        ordered_chain: List[AuditEvent] = []
        curr_prev = GENESIS_PREVIOUS_HASH
        
        while curr_prev in prev_map:
            curr_evt = prev_map[curr_prev]
            ordered_chain.append(curr_evt)
            curr_prev = curr_evt.event_hash

        if len(ordered_chain) != len(events):
            present_types: List[AuditEventType] = [e.event_type for e in ordered_chain]
            expected_types: List[AuditEventType] = [AuditEventType(t) for t in EXPECTED_AUDIT_EVENT_SEQUENCE]
            missing_events: List[AuditEventType] = [t for t in expected_types if t not in present_types]
            return VerificationResult(
                status=VerificationStatus.INVALID,
                chain_length=len(events),
                verified_events=len(ordered_chain),
                missing_events=missing_events,
                failure_reason=f"Chain contains disconnected or floating events (traversed {len(ordered_chain)} of {len(events)}). Missing expected types: {[m.value for m in missing_events]}.",
            )

        # Step 2: Event Self-Integrity & Schema Validation
        verified_count = 0
        for evt in ordered_chain:
            evt_res = self.verify_event(evt)
            if evt_res.status != VerificationStatus.VALID:
                return VerificationResult(
                    status=VerificationStatus.INVALID,
                    chain_length=len(events),
                    verified_events=verified_count,
                    broken_at_event_id=evt.event_id,
                    expected_hash=evt_res.expected_hash,
                    observed_hash=evt_res.observed_hash,
                    failure_reason=evt_res.failure_reason,
                )
            verified_count += 1

        # Step 3: Completeness Validation against EXPECTED_AUDIT_EVENT_SEQUENCE
        present_types: List[AuditEventType] = [e.event_type for e in ordered_chain]
        expected_types: List[AuditEventType] = [AuditEventType(t) for t in EXPECTED_AUDIT_EVENT_SEQUENCE]
        
        missing_events: List[AuditEventType] = [
            t for t in expected_types if t not in present_types
        ]

        if missing_events:
            return VerificationResult(
                status=VerificationStatus.INVALID,
                chain_length=len(events),
                verified_events=verified_count,
                missing_events=missing_events,
                failure_reason=f"Audit chain is incomplete. Missing mandatory event types: {[m.value for m in missing_events]}.",
            )

        # Step 4: Verify Sequence Order matches EXPECTED_AUDIT_EVENT_SEQUENCE
        if present_types != expected_types:
            return VerificationResult(
                status=VerificationStatus.INVALID,
                chain_length=len(events),
                verified_events=verified_count,
                failure_reason=f"Audit event sequence mismatch. Expected {[t.value for t in expected_types]}, got {[t.value for t in present_types]}.",
            )

        # Step 5: Optional Document Checksum Fingerprint Verification
        checksum_status = DocumentChecksumVerification.NOT_AVAILABLE
        if document_bytes is not None:
            computed_checksum = hashlib.sha256(document_bytes).hexdigest()
            genesis_evt = ordered_chain[0]
            stored_checksum = genesis_evt.metadata.get("checksum")
            if stored_checksum and computed_checksum == stored_checksum:
                checksum_status = DocumentChecksumVerification.MATCH
            else:
                checksum_status = DocumentChecksumVerification.MISMATCH
                return VerificationResult(
                    status=VerificationStatus.INVALID,
                    chain_length=len(events),
                    verified_events=verified_count,
                    document_checksum_status=checksum_status,
                    failure_reason=f"Document payload checksum mismatch. Stored: '{stored_checksum}', Computed: '{computed_checksum}'.",
                )

        return VerificationResult(
            status=VerificationStatus.VALID,
            chain_length=len(events),
            verified_events=verified_count,
            document_checksum_status=checksum_status,
        )

    def verify_bundle(self, bundle: AnalysisEvidenceBundle) -> VerificationResult:
        """Verify structural and cryptographic bundle hash integrity."""
        from app.audit.bundle import compute_bundle_hash
        computed_hash = compute_bundle_hash(bundle)
        if computed_hash != bundle.bundle_hash:
            return VerificationResult(
                status=VerificationStatus.INVALID,
                chain_length=1,
                verified_events=0,
                expected_hash=computed_hash,
                observed_hash=bundle.bundle_hash,
                failure_reason=f"Evidence bundle hash mismatch for bundle '{bundle.bundle_id}'.",
            )
        return VerificationResult(
            status=VerificationStatus.VALID,
            chain_length=1,
            verified_events=1,
        )
