import asyncio
import time
import structlog
from typing import Optional, Dict, Any
from datetime import datetime
from backend.config.settings import settings
from backend.services.queue import queue
from backend.services.database import db
from backend.services.github_client import github_client
from backend.services.diff_parser import diff_parser
from backend.models.pr import PRTask, PRReviewStatus
from backend.models.review import ReviewResult, AgentResult, APIUsage
from backend.workers.agents.scout import ScoutAgent
from backend.workers.agents.guardian import GuardianAgent
from backend.workers.agents.architect import ArchitectAgent
from backend.workers.agents.stylist import StylistAgent
from backend.workers.agents.synthesizer import SynthesizerAgent

logger = structlog.get_logger(__name__)


class RateLimiter:
    
    def __init__(self, rate: int, per: int = 60):
        self.rate = rate
        self.per = per
        self.tokens = rate
        self.last_refill = time.time()
        self.lock = asyncio.Lock()
    
    async def acquire(self) -> bool:
        """Acquire a token, return True if successful."""
        async with self.lock:
            now = time.time()
            # Refill tokens
            elapsed = now - self.last_refill
            tokens_to_add = int(elapsed * self.rate / self.per)
            if tokens_to_add > 0:
                self.tokens = min(self.rate, self.tokens + tokens_to_add)
                self.last_refill = now
            
            if self.tokens > 0:
                self.tokens -= 1
                return True
            return False
    
    async def wait(self):
        """Wait until a token is available."""
        while not await self.acquire():
            wait_time = self.per / self.rate
            await asyncio.sleep(wait_time)


class Orchestrator:
    
    def __init__(self):
        self.scout = ScoutAgent()
        self.guardian = GuardianAgent()
        self.architect = ArchitectAgent()
        self.stylist = StylistAgent()
        self.synthesizer = SynthesizerAgent()
        
        # Rate limiters
        self.github_limiter = RateLimiter(settings.github_rate_limit_per_minute, 60)
        self.openai_limiter = RateLimiter(settings.openai_rate_limit_per_minute, 60)
        self.anthropic_limiter = RateLimiter(settings.anthropic_rate_limit_per_minute, 60)
        
        self.running = False
    
    async def start(self):
        self.running = True
        logger.info("Orchestrator started")
        
        # Connect to services
        await db.connect()
        await queue.connect()
        
        # Main loop
        while self.running:
            try:
                task = await queue.dequeue(timeout=settings.worker_poll_interval)
                if task:
                    asyncio.create_task(self.process_task(task))
            except Exception as e:
                logger.error("Error in orchestrator loop", error=str(e))
                await asyncio.sleep(5)
    
    async def stop(self):
        self.running = False
        await db.disconnect()
        await queue.disconnect()
        logger.info("Orchestrator stopped")
    
    async def process_task(self, task: PRTask):
        pr_meta = task.pr_metadata
        pr_id = pr_meta.pr_id
        repository = pr_meta.repository
        
        logger.info("Processing PR task", pr_id=pr_id, repository=repository)
        
        # Create PR review record
        try:
            review_status = await db.create_pr_review(pr_id, repository)
            await db.update_pr_review_status(pr_id, repository, "processing")
        except Exception as e:
            logger.error("Failed to create PR review record", error=str(e))
            return
        
        try:
            # Step 1: Fetch PR diff from GitHub
            await self.github_limiter.wait()
            diff = await github_client.get_pr_diff(
                pr_meta.owner,
                pr_meta.repo_name,
                pr_id,
                pr_meta.installation_id
            )
            
            # Step 2: Process and filter diff
            filtered_diff, files_info = diff_parser.process_diff(diff)
            
            # Step 3: Run Scout agent (filter noise)
            await self.openai_limiter.wait()
            scout_result = await self.scout.analyze(filtered_diff, {
                "repository": repository,
                "pr_id": pr_id,
                "files": files_info
            })
            
            # Step 4: Run Guardian, Architect, and Stylist in parallel
            filtered_for_review = scout_result.output if not scout_result.error else filtered_diff
            
            # Create tasks for parallel execution
            guardian_task = self.guardian.analyze(filtered_for_review, {
                "repository": repository,
                "pr_id": pr_id
            })
            architect_task = self.architect.analyze(filtered_for_review, {
                "repository": repository,
                "pr_id": pr_id
            })
            stylist_task = self.stylist.analyze(filtered_for_review, {
                "repository": repository,
                "pr_id": pr_id,
                "language": self._detect_language(files_info)
            })
            
            # Wait for rate limiters and execute in parallel
            await asyncio.gather(
                self.anthropic_limiter.wait(),
                self.openai_limiter.wait(),
                self.openai_limiter.wait()
            )
            
            guardian_result, architect_result, stylist_result = await asyncio.gather(
                guardian_task,
                architect_task,
                stylist_task,
                return_exceptions=True
            )
            
            # Handle exceptions
            if isinstance(guardian_result, Exception):
                logger.error("Guardian agent exception", error=str(guardian_result))
                guardian_result = AgentResult(
                    agent_name="guardian",
                    output="Security analysis failed",
                    tokens_used=0,
                    model_used=settings.guardian_model,
                    error=str(guardian_result)
                )
            
            if isinstance(architect_result, Exception):
                logger.error("Architect agent exception", error=str(architect_result))
                architect_result = AgentResult(
                    agent_name="architect",
                    output="Architecture analysis failed",
                    tokens_used=0,
                    model_used=settings.architect_model,
                    error=str(architect_result)
                )
            
            if isinstance(stylist_result, Exception):
                logger.error("Stylist agent exception", error=str(stylist_result))
                stylist_result = AgentResult(
                    agent_name="stylist",
                    output="Style analysis failed",
                    tokens_used=0,
                    model_used=settings.stylist_model,
                    error=str(stylist_result)
                )
            
            # Step 5: Run Synthesizer
            await self.openai_limiter.wait()
            pr_details = await github_client.get_pr_details(
                pr_meta.owner,
                pr_meta.repo_name,
                pr_id,
                pr_meta.installation_id
            )
            
            synthesizer_result = await self.synthesizer.analyze(
                scout_result,
                guardian_result,
                architect_result,
                stylist_result,
                {
                    "repository": repository,
                    "pr_id": pr_id,
                    "pr_title": pr_details.get("title", ""),
                    "files_changed": len(files_info)
                }
            )
            
            # Step 6: Create review result
            total_tokens = (
                scout_result.tokens_used +
                guardian_result.tokens_used +
                architect_result.tokens_used +
                stylist_result.tokens_used +
                synthesizer_result.tokens_used
            )
            
            review_result = ReviewResult(
                pr_id=pr_id,
                repository=repository,
                scout_result=scout_result,
                guardian_result=guardian_result,
                architect_result=architect_result,
                stylist_result=stylist_result,
                synthesizer_result=synthesizer_result,
                final_comment=synthesizer_result.output,
                total_tokens=total_tokens,
                metadata={
                    "files_changed": len(files_info),
                    "diff_size": len(diff),
                    "filtered_diff_size": len(filtered_diff)
                }
            )
            
            # Step 7: Save results to database
            await db.save_review_result(review_result)
            
            # Save API usage
            for agent_result in [scout_result, guardian_result, architect_result, stylist_result, synthesizer_result]:
                if agent_result:
                    cost_estimate = self._estimate_cost(agent_result.model_used, agent_result.tokens_used)
                    await db.save_api_usage(APIUsage(
                        pr_id=pr_id,
                        repository=repository,
                        agent_name=agent_result.agent_name,
                        model=agent_result.model_used,
                        tokens_used=agent_result.tokens_used,
                        cost_estimate=cost_estimate
                    ))
            
            # Step 8: Post comment to GitHub
            await self.github_limiter.wait()
            comment_data = await github_client.post_pr_comment(
                pr_meta.owner,
                pr_meta.repo_name,
                pr_id,
                pr_meta.installation_id,
                synthesizer_result.output
            )
            
            # Step 9: Update review status
            await db.update_pr_review_status(
                pr_id,
                repository,
                "completed",
                comment_posted=True,
                comment_id=comment_data.get("id")
            )
            
            logger.info(
                "PR review completed",
                pr_id=pr_id,
                repository=repository,
                total_tokens=total_tokens
            )
        
        except Exception as e:
            logger.error("Error processing PR task", pr_id=pr_id, error=str(e))
            await db.update_pr_review_status(pr_id, repository, "failed", error_message=str(e))
            
            # Move to dead letter queue if retries exceeded
            if task.retry_count >= settings.max_retries:
                await queue.enqueue_dlq(task, str(e))
            else:
                # Retry
                task.retry_count += 1
                await asyncio.sleep(settings.retry_delay * task.retry_count)
                await queue.enqueue(task)
    
    def _detect_language(self, files_info: list) -> str:
        extensions = {}
        for file_info in files_info:
            filepath = file_info.get('new_path') or file_info.get('old_path', '')
            if '.' in filepath:
                ext = filepath.split('.')[-1].lower()
                extensions[ext] = extensions.get(ext, 0) + 1
        
        if not extensions:
            return "unknown"
        
        # Common language extensions
        lang_map = {
            'py': 'python',
            'js': 'javascript',
            'ts': 'typescript',
            'java': 'java',
            'go': 'go',
            'rs': 'rust',
            'cpp': 'c++',
            'c': 'c',
            'rb': 'ruby',
            'php': 'php',
            'swift': 'swift',
            'kt': 'kotlin'
        }
        
        # Find most common extension
        most_common = max(extensions.items(), key=lambda x: x[1])[0]
        return lang_map.get(most_common, most_common)
    
    def _estimate_cost(self, model: str, tokens: int) -> float:
        # Rough cost estimates per 1K tokens (as of 2024)
        costs = {
            "gpt-4o": 0.005,  # $5 per 1M input tokens
            "gpt-4o-mini": 0.00015,  # $0.15 per 1M input tokens
            "claude-3-5-sonnet-20241022": 0.003,  # $3 per 1M input tokens
        }
        
        cost_per_1k = costs.get(model, 0.001)  # Default estimate
        return (tokens / 1000) * cost_per_1k


async def main():
    orchestrator = Orchestrator()
    try:
        await orchestrator.start()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
        await orchestrator.stop()


if __name__ == "__main__":
    asyncio.run(main())

