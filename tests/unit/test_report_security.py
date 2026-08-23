"""Security and boundary unit tests for Phase 12 Report Generation."""

from datetime import datetime, timezone
import importlib
import pkgutil
import pytest

from app.models.document import DocumentMetadata, DocumentStatus
from app.reports.builder import ReportBuilder
from app.reports.errors import ReportIntegrityError
from app.reports.models import ReportContext
from app.reports.validators import validate_identifier


def test_validate_identifier_accepts_safe_strings():
    validate_identifier("document_id", "doc-123-abc_XYZ")
    validate_identifier("workflow_id", "wf_456_DEF-789")


@pytest.mark.parametrize(
    "bad_id",
    [
        "doc/123",
        "doc\\123",
        "../doc123",
        "..\\doc123",
        "doc\x00123",
        "doc\n123",
        "doc 123",
        "doc;123",
        "doc<script>",
        "",
    ],
)
def test_validate_identifier_rejects_unsafe_strings(bad_id):
    with pytest.raises(ReportIntegrityError):
        validate_identifier("test_id", bad_id)


def test_builder_rejects_path_traversal_document_id():
    bad_metadata = DocumentMetadata(
        document_id="../etc/passwd",
        filename="hack.pdf",
        content_type="application/pdf",
        size_bytes=100,
        storage_bucket="bucket",
        storage_object="obj",
        document_status=DocumentStatus.STORED,
        checksum="1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
    )
    ref_dt = datetime(2026, 8, 18, 18, 0, 0, 0, tzinfo=timezone.utc)
    ctx = ReportContext(reference_datetime=ref_dt)

    with pytest.raises(ReportIntegrityError):
        ReportBuilder.build_view_model(document_metadata=bad_metadata, workflow_id="wf-valid-123", report_context=ctx)


def test_reports_package_has_no_gemini_or_network_imports():
    import app.reports as reports_pkg

    package_path = reports_pkg.__path__
    for _, module_name, _ in pkgutil.walk_packages(package_path, prefix="app.reports."):
        mod = importlib.import_module(module_name)
        mod_src = getattr(mod, "__file__", "")
        if mod_src:
            with open(mod_src, "r", encoding="utf-8") as f:
                code = f.read()
                assert "google.genai" not in code
                assert "google.adk" not in code
                assert "httpx" not in code
                assert "requests" not in code


def test_reports_package_has_no_workflow_state_mutation():
    import app.reports as reports_pkg

    package_path = reports_pkg.__path__
    for _, module_name, _ in pkgutil.walk_packages(package_path, prefix="app.reports."):
        mod = importlib.import_module(module_name)
        mod_src = getattr(mod, "__file__", "")
        if mod_src:
            with open(mod_src, "r", encoding="utf-8") as f:
                code = f.read()
                assert "AnalysisWorkflow" not in code
                assert "transition_to(" not in code
