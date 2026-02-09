import time
import structlog
from typing import Dict, Any
from openai import AsyncOpenAI
from backend.config.settings import settings
from backend.models.review import AgentResult

logger = structlog.get_logger(__name__)


class StylistAgent:
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.stylist_model
    
    async def analyze(self, diff: str, context: Dict[str, Any]) -> AgentResult:
        start_time = time.time()
        tokens_used = 0
        
        try:
            # Try to detect language from context or diff
            language = context.get('language', 'unknown')
            
            prompt = f"""You are a code style reviewer. Analyze this Git diff for style and naming issues.

Focus on:
1. Naming Conventions:
   - Variable names (camelCase, snake_case, etc.)
   - Function/method names
   - Class names
   - Constant names
   - File names

2. Code Style:
   - Indentation consistency
   - Spacing and formatting
   - Line length
   - Trailing whitespace
   - Missing/extra blank lines

3. Best Practices:
   - Magic numbers (should be constants)
   - Comment quality
   - Documentation
   - Import organization

4. Language-Specific Linting:
   - Follow common linting rules for {language}
   - Common anti-patterns

Provide feedback in a friendly, constructive manner. Focus on actionable improvements.
If the code style is good, acknowledge that.

Here is the diff:

{diff[:50000]}

Provide a style review with specific suggestions."""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a friendly code style reviewer who provides constructive feedback."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=3000
            )
            
            analysis = response.choices[0].message.content
            tokens_used = response.usage.total_tokens
            processing_time = time.time() - start_time
            
            logger.info(
                "Stylist agent completed",
                tokens_used=tokens_used,
                processing_time=processing_time
            )
            
            return AgentResult(
                agent_name="stylist",
                output=analysis,
                tokens_used=tokens_used,
                model_used=self.model,
                processing_time=processing_time
            )
            
        except Exception as e:
            logger.error("Stylist agent error", error=str(e))
            processing_time = time.time() - start_time
            return AgentResult(
                agent_name="stylist",
                output="Style analysis failed. Please review manually.",
                tokens_used=tokens_used,
                model_used=self.model,
                processing_time=processing_time,
                error=str(e)
            )

