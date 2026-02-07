"""
Celery configuration for background task processing.

This module sets up Celery with Redis as the broker and backend,
configured for asynchronous web scraping tasks.
"""

from celery import Celery
from kombu import Queue


# Initialize Celery app
celery_app = Celery("site_search")

# Configure Celery
celery_app.conf.update(
    # Broker and backend
    broker_url="redis://localhost:6379/0",
    result_backend="redis://localhost:6379/0",
    
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    
    # Timezone
    timezone="UTC",
    enable_utc=True,
    
    # Task execution settings
    task_track_started=True,
    task_time_limit=3600,  # 1 hour maximum per task
    task_soft_time_limit=3300,  # Soft limit at 55 minutes
    
    # Worker settings
    worker_prefetch_multiplier=1,  # One task at a time per worker
    worker_max_tasks_per_child=100,  # Restart worker after 100 tasks (memory management)
    
    # Connection settings
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
    
    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour
    result_backend_transport_options={
        "master_name": "mymaster",
    },
    
    # Task routing
    task_default_queue="celery",
    task_queues=(
        Queue("celery", routing_key="celery"),
        Queue("scraping", routing_key="scraping"),
    ),
    
    # Autodiscovery
    imports=("app.tasks",),
)

# Autodiscover tasks from app.tasks module
celery_app.autodiscover_tasks(["app"])


if __name__ == "__main__":
    celery_app.start()
