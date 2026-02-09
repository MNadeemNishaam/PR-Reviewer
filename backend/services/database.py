import asyncpg
import structlog
from typing import Optional, List, Dict, Any
from datetime import datetime
from backend.config.settings import settings
from backend.models.pr import PRReviewStatus
from backend.models.review import ReviewResult, APIUsage

logger = structlog.get_logger(__name__)


class Database:
    
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        try:
            self.pool = await asyncpg.create_pool(
                settings.database_url,
                min_size=2,
                max_size=10,
                command_timeout=60
            )
            logger.info("Database connection pool created")
            await self._create_tables()
        except Exception as e:
            logger.error("Failed to create database pool", error=str(e))
            raise
    
    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed")
    
    async def _create_tables(self):
        async with self.pool.acquire() as conn:
            # PR Reviews table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS pr_reviews (
                    id SERIAL PRIMARY KEY,
                    pr_id INTEGER NOT NULL,
                    repository VARCHAR(255) NOT NULL,
                    status VARCHAR(50) NOT NULL DEFAULT 'pending',
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    error_message TEXT,
                    comment_posted BOOLEAN DEFAULT FALSE,
                    comment_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(pr_id, repository)
                )
            """)
            
            # Review Results table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS review_results (
                    id SERIAL PRIMARY KEY,
                    pr_id INTEGER NOT NULL,
                    repository VARCHAR(255) NOT NULL,
                    scout_result JSONB,
                    guardian_result JSONB,
                    architect_result JSONB,
                    stylist_result JSONB,
                    synthesizer_result JSONB,
                    final_comment TEXT,
                    total_tokens INTEGER DEFAULT 0,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (pr_id, repository) REFERENCES pr_reviews(pr_id, repository)
                )
            """)
            
            # API Usage table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS api_usage (
                    id SERIAL PRIMARY KEY,
                    pr_id INTEGER NOT NULL,
                    repository VARCHAR(255) NOT NULL,
                    agent_name VARCHAR(100) NOT NULL,
                    model VARCHAR(100) NOT NULL,
                    tokens_used INTEGER NOT NULL,
                    cost_estimate DECIMAL(10, 6) DEFAULT 0.0,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_pr_reviews_status 
                ON pr_reviews(status)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_usage_timestamp 
                ON api_usage(timestamp)
            """)
            
            logger.info("Database tables created/verified")
    
    async def create_pr_review(self, pr_id: int, repository: str) -> PRReviewStatus:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO pr_reviews (pr_id, repository, status, started_at)
                VALUES ($1, $2, 'pending', CURRENT_TIMESTAMP)
                ON CONFLICT (pr_id, repository) 
                DO UPDATE SET status = 'pending', started_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            """, pr_id, repository)
            
            return await self.get_pr_review(pr_id, repository)
    
    async def get_pr_review(self, pr_id: int, repository: str) -> Optional[PRReviewStatus]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT pr_id, repository, status, started_at, completed_at, 
                       error_message, comment_posted, comment_id
                FROM pr_reviews
                WHERE pr_id = $1 AND repository = $2
            """, pr_id, repository)
            
            if not row:
                return None
            
            return PRReviewStatus(
                pr_id=row['pr_id'],
                repository=row['repository'],
                status=row['status'],
                started_at=row['started_at'],
                completed_at=row['completed_at'],
                error_message=row['error_message'],
                comment_posted=row['comment_posted'],
                comment_id=row['comment_id']
            )
    
    async def update_pr_review_status(
        self,
        pr_id: int,
        repository: str,
        status: str,
        error_message: Optional[str] = None,
        comment_posted: bool = False,
        comment_id: Optional[int] = None
    ):
        async with self.pool.acquire() as conn:
            if status == 'completed':
                await conn.execute("""
                    UPDATE pr_reviews
                    SET status = $1, completed_at = CURRENT_TIMESTAMP,
                        error_message = $2, comment_posted = $3, comment_id = $4,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE pr_id = $5 AND repository = $6
                """, status, error_message, comment_posted, comment_id, pr_id, repository)
            elif status == 'failed':
                await conn.execute("""
                    UPDATE pr_reviews
                    SET status = $1, completed_at = CURRENT_TIMESTAMP,
                        error_message = $2, updated_at = CURRENT_TIMESTAMP
                    WHERE pr_id = $3 AND repository = $4
                """, status, error_message, pr_id, repository)
            else:
                await conn.execute("""
                    UPDATE pr_reviews
                    SET status = $1, error_message = $2, updated_at = CURRENT_TIMESTAMP
                    WHERE pr_id = $3 AND repository = $4
                """, status, error_message, pr_id, repository)
    
    async def save_review_result(self, result: ReviewResult):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO review_results (
                    pr_id, repository, scout_result, guardian_result,
                    architect_result, stylist_result, synthesizer_result,
                    final_comment, total_tokens, metadata
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT DO NOTHING
            """,
                result.pr_id,
                result.repository,
                result.scout_result.model_dump_json() if result.scout_result else None,
                result.guardian_result.model_dump_json() if result.guardian_result else None,
                result.architect_result.model_dump_json() if result.architect_result else None,
                result.stylist_result.model_dump_json() if result.stylist_result else None,
                result.synthesizer_result.model_dump_json() if result.synthesizer_result else None,
                result.final_comment,
                result.total_tokens,
                result.metadata
            )
    
    async def save_api_usage(self, usage: APIUsage):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO api_usage (pr_id, repository, agent_name, model, tokens_used, cost_estimate)
                VALUES ($1, $2, $3, $4, $5, $6)
            """,
                usage.pr_id,
                usage.repository,
                usage.agent_name,
                usage.model,
                usage.tokens_used,
                usage.cost_estimate
            )
    
    async def get_recent_usage(self, minutes: int = 60) -> List[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT agent_name, model, SUM(tokens_used) as total_tokens, COUNT(*) as request_count
                FROM api_usage
                WHERE timestamp > NOW() - INTERVAL '%s minutes'
                GROUP BY agent_name, model
            """, minutes)
            
            return [dict(row) for row in rows]


# Global database instance
db = Database()

