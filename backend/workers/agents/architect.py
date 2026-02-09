import time
import structlog
from typing import Dict, Any
from openai import AsyncOpenAI
from backend.config.settings import settings
from backend.models.review import AgentResult

logger = structlog.get_logger(__name__)


class ArchitectAgent:
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.architect_model
    
    async def analyze(self, diff: str, context: Dict[str, Any]) -> AgentResult:
        start_time = time.time()
        tokens_used = 0
        
        try:
            prompt = f"""You are a senior software architect reviewing code changes. Analyze this Git diff for:

1. Logic Flow Issues:
   - Missing error handling
   - Incorrect control flow
   - Race conditions
   - Dead code
   - Infinite loops or recursion issues

2. Code Complexity:
   - Cyclomatic complexity
   - Nested conditionals
   - Long functions/methods
   - Cognitive complexity

3. DRY (Don't Repeat Yourself) Violations:
   - Code duplication
   - Opportunities for abstraction
   - Missing utility functions

4. Design Patterns:
   - Appropriate use of design patterns
   - Missing abstractions
   - Tight coupling
   - Poor separation of concerns

5. Performance:
   - Inefficient algorithms
   - Unnecessary database queries
   - Memory leaks
   - Resource management

For each issue, provide:
- Type of issue
- Location (file/function if identifiable)
- Impact
- Suggested improvement

Here is the diff:

{diff[:50000]}

Provide a comprehensive architectural review."""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a senior software architect with expertise in code quality, design patterns, and best practices."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=4000
            )
            
            analysis = response.choices[0].message.content
            tokens_used = response.usage.total_tokens
            processing_time = time.time() - start_time
            
            logger.info(
                "Architect agent completed",
                tokens_used=tokens_used,
                processing_time=processing_time
            )
            
            return AgentResult(
                agent_name="architect",
                output=analysis,
                tokens_used=tokens_used,
                model_used=self.model,
                processing_time=processing_time
            )
            
        except Exception as e:
            logger.error("Architect agent error", error=str(e))
            processing_time = time.time() - start_time
            return AgentResult(
                agent_name="architect",
                output="Architectural analysis failed. Please review manually.",
                tokens_used=tokens_used,
                model_used=self.model,
                processing_time=processing_time,
                error=str(e)
            )

