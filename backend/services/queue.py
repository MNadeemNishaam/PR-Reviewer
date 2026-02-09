import json
import redis.asyncio as redis
import structlog
from typing import Optional
from datetime import datetime
from backend.config.settings import settings
from backend.models.pr import PRTask

logger = structlog.get_logger(__name__)


class Queue:
    
    def __init__(self):
        self.client: Optional[redis.Redis] = None
        self.queue_name = "pr_review_queue"
        self.dead_letter_queue = "pr_review_dlq"
    
    async def connect(self):
        """Connect to Redis."""
        try:
            # Parse Redis URL (Upstash format: redis://default:password@host:port)
            self.client = await redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # Test connection
            await self.client.ping()
            logger.info("Connected to Redis")
        except Exception as e:
            logger.error("Failed to connect to Redis", error=str(e))
            raise
    
    async def disconnect(self):
        if self.client:
            await self.client.close()
            logger.info("Disconnected from Redis")
    
    async def enqueue(self, task: PRTask) -> bool:
        try:
            task_data = task.model_dump_json()
            await self.client.lpush(self.queue_name, task_data)
            logger.info("Task enqueued", pr_id=task.pr_metadata.pr_id, repository=task.pr_metadata.repository)
            return True
        except Exception as e:
            logger.error("Failed to enqueue task", error=str(e))
            return False
    
    async def dequeue(self, timeout: int = 5) -> Optional[PRTask]:
        try:
            # Blocking pop with timeout
            result = await self.client.brpop(self.queue_name, timeout=timeout)
            if result:
                _, task_data = result
                task_dict = json.loads(task_data)
                # Parse datetime strings
                if 'queued_at' in task_dict and isinstance(task_dict['queued_at'], str):
                    task_dict['queued_at'] = datetime.fromisoformat(task_dict['queued_at'].replace('Z', '+00:00'))
                return PRTask(**task_dict)
            return None
        except redis.TimeoutError:
            return None
        except Exception as e:
            logger.error("Failed to dequeue task", error=str(e))
            return None
    
    async def enqueue_dlq(self, task: PRTask, error: str):
        try:
            task_data = task.model_dump_json()
            error_data = {
                "task": task_data,
                "error": error,
                "failed_at": datetime.utcnow().isoformat()
            }
            await self.client.lpush(self.dead_letter_queue, json.dumps(error_data))
            logger.warning("Task moved to DLQ", pr_id=task.pr_metadata.pr_id, error=error)
        except Exception as e:
            logger.error("Failed to enqueue to DLQ", error=str(e))
    
    async def get_queue_length(self) -> int:
        try:
            return await self.client.llen(self.queue_name)
        except Exception as e:
            logger.error("Failed to get queue length", error=str(e))
            return 0
    
    async def clear_queue(self):
        try:
            await self.client.delete(self.queue_name)
            logger.warning("Queue cleared")
        except Exception as e:
            logger.error("Failed to clear queue", error=str(e))


# Global queue instance
queue = Queue()

