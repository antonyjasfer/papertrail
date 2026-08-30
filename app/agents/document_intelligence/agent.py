import logging
import time
from typing import Any, Optional
from pydantic import ValidationError

from google import genai
from google.genai import types

from app.agents.document_intelligence.prompts import SYSTEM_PROMPT, TASK_PROMPT
from app.agents.document_intelligence.schemas import GeminiExtractionPayload
from app.core.config import settings
from app.core.gcp import gcp_foundation

logger = logging.getLogger("papertrail.agents.document_intelligence")


class DocumentIntelligenceAgentError(Exception):
    """Exception raised when DocumentIntelligenceAgent fails to process a document payload."""

    def __init__(self, message: str, is_transient: bool = False):
        self.is_transient = is_transient
        super().__init__(f"Document Intelligence Agent error: {message}")


class DocumentIntelligenceAgent:
    """Agent executing multimodal document understanding and structured extraction using Gemini 3.5 Flash."""

    def __init__(
        self,
        client: Optional[Any] = None,
        model_name: Optional[str] = None,
        max_retries: Optional[int] = None,
    ):
        self._client = client
        self.model_name = model_name or settings.gemini_model
        self.max_retries = max_retries if max_retries is not None else settings.max_retries

    @property
    def client(self) -> Any:
        """Lazily initialize and return google.genai.Client instance."""
        if self._client is None:
            api_key = settings.gemini_api_key
            if not api_key:
                if settings.papertrail_cloud_provider == "azure" or settings.azure_keyvault_url:
                    try:
                        from app.infrastructure.azure.key_vault_provider import AzureKeyVaultSecretProvider
                        kv = AzureKeyVaultSecretProvider()
                        api_key = kv.get_secret("gemini-api-key")
                        logger.info("Successfully fetched Gemini API key from Azure Key Vault")
                    except Exception as kv_err:
                        logger.warning("Azure Key Vault key retrieval attempt failed: %s", kv_err)
                else:
                    # Attempt retrieval from Secret Manager fallback if configured
                    secret_client = gcp_foundation.get_secret_manager_client()
                    if secret_client:
                        try:
                            secret_name = (
                                f"projects/{settings.gcp_project_id}/secrets/{settings.secret_name_gemini_api_key}/versions/latest"
                            )
                            response = secret_client.access_secret_version(request={"name": secret_name})
                            api_key = response.payload.data.decode("utf-8").strip()
                            logger.info("Successfully fetched Gemini API key from Secret Manager")
                        except Exception as err:
                            logger.warning("Secret Manager key retrieval attempt failed: %s", err)

            try:
                if api_key:
                    self._client = genai.Client(api_key=api_key)
                else:
                    # Fallback to Application Default Credentials (ADC)
                    self._client = genai.Client()
                logger.info("Successfully initialized google.genai.Client for model '%s'", self.model_name)
            except Exception as err:
                raise DocumentIntelligenceAgentError(
                    f"Failed to initialize Gemini Client: {err}", is_transient=False
                ) from err

        return self._client

    def extract_document_payload(
        self,
        file_bytes: bytes,
        content_type: str,
        filename: str = "document.bin",
    ) -> GeminiExtractionPayload:
        """Invoke Gemini 3.5 Flash with multimodal document bytes to produce structured GeminiExtractionPayload.

        Executes bounded retries (max_retries=2) for transient network timeouts or rate limit exceptions.
        """
        if not file_bytes:
            raise DocumentIntelligenceAgentError("Document file bytes payload is empty.", is_transient=False)

        # Prepare multimodal document part
        normalized_content_type = content_type.lower().split(";")[0].strip()
        if normalized_content_type in {"application/pdf", "image/png", "image/jpeg", "image/jpg"}:
            document_part = types.Part.from_bytes(data=file_bytes, mime_type=normalized_content_type)
        elif normalized_content_type.startswith("text/"):
            try:
                text_content = file_bytes.decode("utf-8", errors="replace")
                document_part = f"DOCUMENT FILENAME: {filename}\nDOCUMENT CONTENT:\n{text_content}"
            except Exception as err:
                raise DocumentIntelligenceAgentError(f"Text decoding failed: {err}", is_transient=False) from err
        else:
            raise DocumentIntelligenceAgentError(
                f"Unsupported content type '{content_type}' for document intelligence extraction.",
                is_transient=False,
            )

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=GeminiExtractionPayload,
            temperature=0.0,  # Deterministic factual extraction
        )

        attempts = 0
        last_exception: Optional[Exception] = None

        while attempts <= self.max_retries:
            attempts += 1
            try:
                logger.info(
                    "Executing Gemini document extraction (Attempt %d/%d) for '%s' (%s)",
                    attempts,
                    self.max_retries + 1,
                    filename,
                    normalized_content_type,
                )
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=[document_part, TASK_PROMPT],
                    config=config,
                )

                if not response or not response.text:
                    raise DocumentIntelligenceAgentError("Gemini API returned an empty response.", is_transient=True)

                # Parsed structured output via SDK or Pydantic validation
                if hasattr(response, "parsed") and response.parsed and isinstance(response.parsed, GeminiExtractionPayload):
                    return response.parsed

                # Fallback to Pydantic model parsing from response text JSON
                try:
                    payload = GeminiExtractionPayload.model_validate_json(response.text)
                    return payload
                except ValidationError as val_err:
                    logger.error("Pydantic validation failure on Gemini response text: %s", val_err)
                    raise DocumentIntelligenceAgentError(
                        f"Schema validation failure on extraction output: {val_err}", is_transient=False
                    ) from val_err

            except DocumentIntelligenceAgentError as agent_err:
                last_exception = agent_err
                if not agent_err.is_transient or attempts > self.max_retries:
                    raise
            except Exception as err:
                last_exception = err
                err_msg = str(err).lower()
                is_transient = "timeout" in err_msg or "rate limit" in err_msg or "429" in err_msg or "503" in err_msg
                logger.warning("Gemini invocation failed (Attempt %d): %s (transient=%s)", attempts, err, is_transient)

                if not is_transient or attempts > self.max_retries:
                    raise DocumentIntelligenceAgentError(
                        f"Gemini API error during extraction: {err}", is_transient=is_transient
                    ) from err

                time.sleep(1.0 * attempts)  # Backoff delay for transient retry

        raise DocumentIntelligenceAgentError(
            f"Extraction failed after {attempts} attempts: {last_exception}", is_transient=True
        )
