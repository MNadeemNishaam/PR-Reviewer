import time
import structlog
from typing import Dict, Any
from openai import AsyncOpenAI
from backend.config.settings import settings
from backend.models.review import AgentResult

logger = structlog.get_logger(__name__)


class ScoutAgent:
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.scout_model
    
    async def analyze(self, diff: str, context: Dict[str, Any]) -> AgentResult:
        start_time = time.time()
        tokens_used = 0
        
        try:
            # Prepare prompt
            prompt = f"""You are a code review assistant. Your task is to filter a Git diff and identify the most relevant code changes for review.

Focus on:
- Functional code changes (not comments, whitespace-only changes, or formatting)
- Logic modifications
- New features or bug fixes
- Important refactoring

Ignore:
- Lock file changes (package-lock.json, yarn.lock, etc.)
- Generated files
- Binary files
- Whitespace-only changes
- Comment-only changes

Here is the diff:

{diff[:50000]}  # Limit to 50k chars to avoid token limits

Please provide a filtered version of the diff that contains only the relevant code changes for review. If the diff is already clean, return it as-is. Format your response as a Git unified diff."""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a code review assistant that filters Git diffs to show only relevant changes."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=8000
            )
            
            filtered_diff = response.choices[0].message.content
            tokens_used = response.usage.total_tokens
            processing_time = time.time() - start_time
            
            logger.info(
                "Scout agent completed",
                tokens_used=tokens_used,
                processing_time=processing_time,
                original_size=len(diff),
                filtered_size=len(filtered_diff)
            )
            
            return AgentResult(
                agent_name="scout",
                output=filtered_diff,
                tokens_used=tokens_used,
                model_used=self.model,
                processing_time=processing_time
            )
            
        except Exception as e:
            logger.error("Scout agent error", error=str(e))
            processing_time = time.time() - start_time
            return AgentResult(
                agent_name="scout",
                output=diff,  # Return original diff on error
                tokens_used=tokens_used,
                model_used=self.model,
                processing_time=processing_time,
                error=str(e)
            )

