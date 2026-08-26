import pytest
from unittest.mock import MagicMock, patch

from app.api.dependencies import (
    get_document_storage_service,
    resolve_document_bucket_or_container,
)
from app.core.config import settings
from app.core.contracts.storage import IStorageProvider
from app.infrastructure.azure.blob_storage import AzureBlobStorageProvider
from app.infrastructure.factory import get_storage_provider
from app.infrastructure.gcp.storage import GCSStorageProvider
from app.infrastructure.mock.storage import MockStorageProvider
from app.models.document import DocumentStatus
from app.services.document_storage import (
    DocumentStorageError,
    DocumentStorageService,
)


def test_azure_factory_returns_azure_blob_storage_provider():
    """Test: Azure factory returns AzureBlobStorageProvider conforming to IStorageProvider."""
    provider = get_storage_provider("azure")
    assert isinstance(provider, AzureBlobStorageProvider)
    assert isinstance(provider, IStorageProvider)


def test_gcp_factory_returns_gcs_storage_provider_not_azure():
    """Test: GCP factory returns GCSStorageProvider and never returns Azure provider."""
    provider = get_storage_provider("gcp")
    assert isinstance(provider, GCSStorageProvider)
    assert not isinstance(provider, AzureBlobStorageProvider)
    assert isinstance(provider, IStorageProvider)


def test_mock_factory_returns_mock_storage_provider():
    """Test: Mock factory returns MockStorageProvider and does not use Azure/GCP SDKs."""
    provider = get_storage_provider("mock")
    assert isinstance(provider, MockStorageProvider)
    assert not isinstance(provider, AzureBlobStorageProvider)
    assert not isinstance(provider, GCSStorageProvider)
    assert isinstance(provider, IStorageProvider)


def test_document_storage_service_delegates_upload_through_istorageprovider():
    """Test: DocumentStorageService delegates upload explicitly through IStorageProvider."""
    mock_provider = MagicMock(spec=IStorageProvider)
    mock_repo = MagicMock()

    service = DocumentStorageService(
        repository=mock_repo,
        storage_provider=mock_provider,
        bucket_name="test-custom-container",
    )

    payload = b"%PDF-1.4 Mock Upload Test"
    meta = service.store_document(
        filename="custom_doc.pdf",
        content_type="application/pdf",
        file_bytes=payload,
    )

    # Verify IStorageProvider.upload_bytes was called with correct parameters
    mock_provider.upload_bytes.assert_called_once_with(
        bucket_or_container="test-custom-container",
        object_path=meta.storage_object,
        data=payload,
        content_type="application/pdf",
    )
    assert meta.document_status == DocumentStatus.STORED
    mock_repo.create.assert_called_once_with(meta)


def test_document_storage_service_fails_closed_without_provider():
    """Test: DocumentStorageService fails closed with DocumentStorageError if no provider is configured."""
    mock_repo = MagicMock()
    service = DocumentStorageService(
        repository=mock_repo,
        storage_provider=None,
        bucket_name="test-container",
    )

    # 1. Upload must fail closed
    with pytest.raises(DocumentStorageError) as exc_info_upload:
        service.store_document(
            filename="fail_closed.pdf",
            content_type="application/pdf",
            file_bytes=b"sample",
        )
    assert "upload_bytes" in str(exc_info_upload.value)
    assert "fail-closed" in str(exc_info_upload.value)

    # 2. Download must fail closed
    mock_meta = MagicMock()
    mock_meta.document_status = DocumentStatus.STORED
    mock_meta.storage_bucket = "test-container"
    mock_meta.storage_object = "documents/doc-1/original/test.pdf"
    mock_repo.get.return_value = mock_meta

    with pytest.raises(DocumentStorageError) as exc_info_download:
        service.get_document_bytes("doc-1")
    assert "download_bytes" in str(exc_info_download.value)
    assert "fail-closed" in str(exc_info_download.value)

    # 3. Delete must fail closed
    with pytest.raises(DocumentStorageError) as exc_info_delete:
        service.delete_document("doc-1")
    assert "delete_object" in str(exc_info_delete.value)
    assert "fail-closed" in str(exc_info_delete.value)


def test_azure_and_gcp_container_name_resolution():
    """Test: Resolution correctly picks settings.azure_blob_container_documents vs settings.gcs_bucket_documents."""
    azure_container = resolve_document_bucket_or_container("azure")
    assert azure_container == settings.azure_blob_container_documents

    gcp_bucket = resolve_document_bucket_or_container("gcp")
    assert gcp_bucket == settings.gcs_bucket_documents


def test_fastapi_dependency_injects_selected_provider():
    """Test: FastAPI dependency get_document_storage_service injects configured provider and bucket."""
    with patch.object(settings, "papertrail_cloud_provider", "azure"):
        service = get_document_storage_service()
        assert isinstance(service._storage_provider, AzureBlobStorageProvider)
        assert service.bucket_name == settings.azure_blob_container_documents

    with patch.object(settings, "papertrail_cloud_provider", "gcp"):
        service = get_document_storage_service()
        assert isinstance(service._storage_provider, GCSStorageProvider)
        assert service.bucket_name == settings.gcs_bucket_documents

    with patch.object(settings, "papertrail_cloud_provider", "mock"):
        service = get_document_storage_service()
        assert isinstance(service._storage_provider, MockStorageProvider)


def test_zero_cross_cloud_fallback():
    """Test: Failure in Azure provider does NOT fall back to GCP, and vice versa."""
    # 1. Azure provider raises error
    mock_azure = MagicMock(spec=IStorageProvider)
    mock_azure.upload_bytes.side_effect = RuntimeError("Azure Blob connection timeout")
    mock_repo = MagicMock()

    service = DocumentStorageService(
        repository=mock_repo,
        storage_provider=mock_azure,
        bucket_name="azure-container",
    )

    with patch("app.core.gcp.gcp_foundation.get_storage_client") as mock_gcp:
        with pytest.raises(DocumentStorageError) as exc:
            service.store_document("test.pdf", "application/pdf", b"test bytes")
        # Ensure GCP was never invoked
        mock_gcp.assert_not_called()
        assert "upload_bytes" in str(exc.value)

    # 2. GCS provider raises error
    mock_gcs = MagicMock(spec=IStorageProvider)
    mock_gcs.upload_bytes.side_effect = RuntimeError("GCS bucket unavailable")

    service_gcp = DocumentStorageService(
        repository=mock_repo,
        storage_provider=mock_gcs,
        bucket_name="gcp-bucket",
    )

    with patch("app.infrastructure.azure.foundation.azure_foundation.get_blob_service_client") as mock_az:
        with pytest.raises(DocumentStorageError) as exc_gcp:
            service_gcp.store_document("test.pdf", "application/pdf", b"test bytes")
        # Ensure Azure was never invoked
        mock_az.assert_not_called()
        assert "upload_bytes" in str(exc_gcp.value)
