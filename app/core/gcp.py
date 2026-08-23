import logging
from typing import Any, Optional
from app.core.config import settings

logger = logging.getLogger("papertrail.gcp")


class GCPFoundation:
    """Google Cloud Client Foundation Manager.

    Provides centralized client initialization helper functions for Firestore,
    Cloud Storage, Pub/Sub, and Secret Manager without auto-connecting on module import.
    Supports Application Default Credentials (ADC) and local development fallbacks.
    """

    def __init__(self):
        self.project_id = settings.gcp_project_id
        self.region = settings.gcp_region
        self.environment = settings.environment

    def get_firestore_client(self) -> Optional[Any]:
        """Initialize and return Google Cloud Firestore client.

        Returns None if credentials/services are unavailable in development mode.
        """
        try:
            from google.cloud import firestore

            client = firestore.Client(
                project=self.project_id,
                database=settings.firestore_database_id,
            )
            logger.info("Firestore client initialized for project: %s", self.project_id)
            return client
        except Exception as err:
            logger.warning(
                "Firestore client unavailable in environment '%s' (%s). Local fallback active.",
                self.environment,
                err,
            )
            return None

    def get_storage_client(self) -> Optional[Any]:
        """Initialize and return Google Cloud Storage client.

        Returns None if credentials/services are unavailable in development mode.
        """
        try:
            from google.cloud import storage

            client = storage.Client(project=self.project_id)
            logger.info("Cloud Storage client initialized for project: %s", self.project_id)
            return client
        except Exception as err:
            logger.warning(
                "Cloud Storage client unavailable in environment '%s' (%s). Local fallback active.",
                self.environment,
                err,
            )
            return None

    def get_pubsub_publisher(self) -> Optional[Any]:
        """Initialize and return Pub/Sub Publisher client.

        Returns None if credentials/services are unavailable in development mode.
        """
        try:
            from google.cloud import pubsub_v1

            publisher = pubsub_v1.PublisherClient()
            logger.info("Pub/Sub Publisher client initialized for project: %s", self.project_id)
            return publisher
        except Exception as err:
            logger.warning(
                "Pub/Sub Publisher client unavailable in environment '%s' (%s). Local fallback active.",
                self.environment,
                err,
            )
            return None

    def get_pubsub_subscriber(self) -> Optional[Any]:
        """Initialize and return Pub/Sub Subscriber client.

        Returns None if credentials/services are unavailable in development mode.
        """
        try:
            from google.cloud import pubsub_v1

            subscriber = pubsub_v1.SubscriberClient()
            logger.info("Pub/Sub Subscriber client initialized for project: %s", self.project_id)
            return subscriber
        except Exception as err:
            logger.warning(
                "Pub/Sub Subscriber client unavailable in environment '%s' (%s). Local fallback active.",
                self.environment,
                err,
            )
            return None

    def get_secret_manager_client(self) -> Optional[Any]:
        """Initialize and return Secret Manager client.

        Returns None if credentials/services are unavailable in development mode.
        """
        try:
            from google.cloud import secretmanager

            client = secretmanager.SecretManagerServiceClient()
            logger.info("Secret Manager client initialized for project: %s", self.project_id)
            return client
        except Exception as err:
            logger.warning(
                "Secret Manager client unavailable in environment '%s' (%s). Local fallback active.",
                self.environment,
                err,
            )
            return None


gcp_foundation = GCPFoundation()
