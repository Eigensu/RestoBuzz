"""Background alert tasks executed via Celery.

NOTE: Template and Unread alerts have been migrated to FastAPI BackgroundTasks 
in the AlertService for better responsiveness and multi-recipient support.
Legacy tasks have been removed to prevent duplicate alerting.
"""

from app.workers.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger(__name__)

# Currently no active alert tasks here. 
# They have been moved to app.services.alert_service.alert_service
