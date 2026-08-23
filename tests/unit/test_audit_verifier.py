import json
import os
import pytest

from app.audit.models import AnalysisEvidenceBundle, AuditEvent, DocumentChecksumVerification, VerificationStatus
from app.audit.verifier import AuditVerificationService

FIXTURES_DIR = os.path.join("tests", "fixtures", "audit")


def load_fixture_chain(filename: str):
    path = os.path.join(FIXTURES_DIR, filename)
    with open(path, "r") as f:
        data = json.load(f)
    return [AuditEvent(**item) for item in data]


def load_fixture_bundle(filename: str):
    path = os.path.join(FIXTURES_DIR, filename)
    with open(path, "r") as f:
        data = json.load(f)
    return AnalysisEvidenceBundle(**data)


@pytest.fixture
def verifier():
    return AuditVerificationService()


def test_verify_clean_chain(verifier):
    chain = load_fixture_chain("clean_audit_chain.json")
    res = verifier.verify_chain(chain)
    assert res.status == VerificationStatus.VALID
    assert res.chain_length == 6
    assert res.verified_events == 6
    assert res.document_checksum_status == DocumentChecksumVerification.NOT_AVAILABLE


def test_valid_chain_is_order_independent_of_input_list(verifier):
    """Confirm that supplying valid chain events in a shuffled Python list order yields VALID."""
    chain = load_fixture_chain("clean_audit_chain.json")
    shuffled_chain = [chain[3], chain[0], chain[5], chain[1], chain[4], chain[2]]
    res = verifier.verify_chain(shuffled_chain)
    assert res.status == VerificationStatus.VALID
    assert res.chain_length == 6
    assert res.verified_events == 6


def test_verify_clean_chain_with_document_bytes_match(verifier):
    chain = load_fixture_chain("clean_audit_chain.json")
    doc_bytes = b""  # SHA-256 of empty bytes is e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
    res = verifier.verify_chain(chain, document_bytes=doc_bytes)
    assert res.status == VerificationStatus.VALID
    assert res.document_checksum_status == DocumentChecksumVerification.MATCH


def test_verify_clean_chain_with_document_bytes_mismatch(verifier):
    chain = load_fixture_chain("clean_audit_chain.json")
    doc_bytes = b"different content"
    res = verifier.verify_chain(chain, document_bytes=doc_bytes)
    assert res.status == VerificationStatus.INVALID
    assert res.document_checksum_status == DocumentChecksumVerification.MISMATCH
    assert "checksum mismatch" in res.failure_reason


def test_verify_tampered_payload(verifier):
    chain = load_fixture_chain("tampered_payload.json")
    res = verifier.verify_chain(chain)
    assert res.status == VerificationStatus.INVALID
    assert res.broken_at_event_id is not None
    assert "self-hash mismatch" in res.failure_reason


def test_verify_tampered_previous_hash(verifier):
    chain = load_fixture_chain("tampered_previous_hash.json")
    res = verifier.verify_chain(chain)
    assert res.status == VerificationStatus.INVALID
    assert "traversed" in res.failure_reason or "floating" in res.failure_reason


def test_verify_missing_forensic_event(verifier):
    chain = load_fixture_chain("missing_forensic_event.json")
    res = verifier.verify_chain(chain)
    assert res.status == VerificationStatus.INVALID
    assert len(res.missing_events) > 0
    assert "FORENSIC_ANALYSIS_COMPLETED" in [m.value for m in res.missing_events]


def test_verify_reordered_events(verifier):
    chain = load_fixture_chain("reordered_events.json")
    res = verifier.verify_chain(chain)
    assert res.status == VerificationStatus.INVALID
    assert "sequence mismatch" in res.failure_reason or "floating" in res.failure_reason


def test_verify_schema_version_mismatch(verifier):
    chain = load_fixture_chain("schema_version_mismatch.json")
    res = verifier.verify_chain(chain)
    assert res.status == VerificationStatus.INVALID
    assert "Unsupported schema version" in res.failure_reason


def test_verify_valid_bundle(verifier):
    bundle = load_fixture_bundle("valid_analysis_bundle.json")
    res = verifier.verify_bundle(bundle)
    assert res.status == VerificationStatus.VALID
