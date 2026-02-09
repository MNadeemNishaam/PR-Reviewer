import time
import structlog
from typing import Dict, Any
from anthropic import AsyncAnthropic
from backend.config.settings import settings
from backend.models.review import AgentResult

logger = structlog.get_logger(__name__)


class GuardianAgent:
    
    def __init__(self):
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.guardian_model
    
    async def analyze(self, diff: str, context: Dict[str, Any]) -> AgentResult:
        """Analyze diff for security issues."""
        start_time = time.time()
        tokens_used = 0
        
        try:
            prompt = f"""You are a security expert reviewing code changes. Analyze this Git diff for security vulnerabilities.

Focus on:
1. Hardcoded secrets (API keys, passwords, tokens, credentials)
2. SQL injection vulnerabilities
3. XSS (Cross-Site Scripting) vulnerabilities
4. CSRF (Cross-Site Request Forgery) issues
5. Authentication and authorization flaws
6. Insecure data storage
7. Insecure communication
8. OWASP Top 10 vulnerabilities

For each issue found, provide:
- Severity (Critical, High, Medium, Low)
- Location (file and line number if possible)
- Description of the vulnerability
- Recommended fix

Here is the diff:

{diff[:50000]}

Provide a detailed security analysis. If no issues are found, state that clearly."""

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            
            analysis = response.content[0].text
            # Estimate tokens (Claude doesn't provide exact usage in response)
            tokens_used = len(prompt.split()) + len(analysis.split())  # Rough estimate
            processing_time = time.time() - start_time
            
            logger.info(
                "Guardian agent completed",
                tokens_used=tokens_used,
                processing_time=processing_time
            )
            
            return AgentResult(
                agent_name="guardian",
                output=analysis,
                tokens_used=tokens_used,
                model_used=self.model,
                processing_time=processing_time
            )
            
        except Exception as e:
            logger.error("Guardian agent error", error=str(e))
            processing_time = time.time() - start_time
            return AgentResult(
                agent_name="guardian",
                output="Security analysis failed. Please review manually.",
                tokens_used=tokens_used,
                model_used=self.model,
                processing_time=processing_time,
                error=str(e)
            )

