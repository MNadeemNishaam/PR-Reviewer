import time
import structlog
from typing import Dict, Any, List
from openai import AsyncOpenAI
from backend.config.settings import settings
from backend.models.review import AgentResult

logger = structlog.get_logger(__name__)


class SynthesizerAgent:
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.synthesizer_model
    
    async def analyze(
        self,
        scout_result: AgentResult,
        guardian_result: AgentResult,
        architect_result: AgentResult,
        stylist_result: AgentResult,
        context: Dict[str, Any]
    ) -> AgentResult:
        """Synthesize all agent results into a cohesive PR comment."""
        start_time = time.time()
        tokens_used = 0
        
        try:
            # Build synthesis prompt
            prompt = f"""You are a senior developer synthesizing code review feedback from multiple specialized reviewers.

Your task is to create a single, cohesive, and friendly PR review comment that:
1. Summarizes the key findings from all reviewers
2. Prioritizes issues by severity/importance
3. Provides actionable feedback
4. Maintains a constructive, professional tone
5. Uses proper Markdown formatting for GitHub

Here are the individual reviews:

## Security Review (Guardian):
{guardian_result.output if guardian_result and not guardian_result.error else "No security issues found or analysis unavailable."}

## Architecture Review (Architect):
{architect_result.output if architect_result and not architect_result.error else "No architectural issues found or analysis unavailable."}

## Style Review (Stylist):
{stylist_result.output if stylist_result and not stylist_result.error else "Code style looks good or analysis unavailable."}

## Context:
- Repository: {context.get('repository', 'unknown')}
- PR Title: {context.get('pr_title', 'unknown')}
- Files Changed: {context.get('files_changed', 'unknown')}

Create a well-structured PR review comment that:
- Starts with a brief summary
- Groups findings by category (Security, Architecture, Style)
- Highlights critical issues first
- Provides specific, actionable suggestions
- Ends on a positive note

Format the output as GitHub Markdown."""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a senior developer who writes clear, constructive, and actionable code review comments."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=4000
            )
            
            synthesized_comment = response.choices[0].message.content
            tokens_used = response.usage.total_tokens
            processing_time = time.time() - start_time
            
            logger.info(
                "Synthesizer agent completed",
                tokens_used=tokens_used,
                processing_time=processing_time
            )
            
            return AgentResult(
                agent_name="synthesizer",
                output=synthesized_comment,
                tokens_used=tokens_used,
                model_used=self.model,
                processing_time=processing_time
            )
            
        except Exception as e:
            logger.error("Synthesizer agent error", error=str(e))
            processing_time = time.time() - start_time
            
            # Fallback: create a simple comment from available results
            fallback_comment = self._create_fallback_comment(
                scout_result, guardian_result, architect_result, stylist_result
            )
            
            return AgentResult(
                agent_name="synthesizer",
                output=fallback_comment,
                tokens_used=tokens_used,
                model_used=self.model,
                processing_time=processing_time,
                error=str(e)
            )
    
    def _create_fallback_comment(
        self,
        scout_result: AgentResult,
        guardian_result: AgentResult,
        architect_result: AgentResult,
        stylist_result: AgentResult
    ) -> str:
        comment_parts = ["## Code Review Summary\n\n"]
        
        if guardian_result and not guardian_result.error:
            comment_parts.append("### Security Review\n")
            comment_parts.append(guardian_result.output)
            comment_parts.append("\n\n")
        
        if architect_result and not architect_result.error:
            comment_parts.append("### Architecture Review\n")
            comment_parts.append(architect_result.output)
            comment_parts.append("\n\n")
        
        if stylist_result and not stylist_result.error:
            comment_parts.append("### Style Review\n")
            comment_parts.append(stylist_result.output)
            comment_parts.append("\n\n")
        
        return "".join(comment_parts)

