import hmac
import hashlib
import json
import structlog
from typing import Dict, Any, Optional
from fastapi import Request, HTTPException, Header
from backend.config.settings import settings
from backend.services.queue import queue
from backend.models.pr import PRMetadata, PRTask

logger = structlog.get_logger(__name__)


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    if not signature:
        return False
    
    # GitHub sends signature as "sha256=hash"
    if not signature.startswith("sha256="):
        return False
    
    expected_signature = signature[7:]  # Remove "sha256=" prefix
    
    # Compute HMAC
    secret = settings.github_webhook_secret.encode('utf-8')
    computed_hash = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    
    # Use constant-time comparison
    return hmac.compare_digest(computed_hash, expected_signature)


async def handle_webhook(request: Request, x_github_event: str = Header(...), x_github_delivery: str = Header(...)) -> Dict[str, str]:
    try:
        # Get raw body for signature verification
        body = await request.body()
        
        # Verify signature
        x_hub_signature_256 = request.headers.get("X-Hub-Signature-256", "")
        if not verify_webhook_signature(body, x_hub_signature_256):
            logger.warning("Invalid webhook signature", delivery_id=x_github_delivery)
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Parse payload
        payload = json.loads(body.decode('utf-8'))
        event_type = x_github_event
        
        logger.info("Webhook received", event_type=event_type, delivery_id=x_github_delivery)
        
        # Handle pull request events
        if event_type == "pull_request":
            action = payload.get("action")
            
            # Only process opened and synchronize events
            if action in ["opened", "synchronize"]:
                pr_data = payload.get("pull_request", {})
                repository = payload.get("repository", {})
                installation = payload.get("installation", {})
                
                # Extract PR metadata
                pr_metadata = PRMetadata(
                    pr_id=pr_data.get("number"),
                    repository=repository.get("full_name"),
                    owner=repository.get("owner", {}).get("login"),
                    repo_name=repository.get("name"),
                    title=pr_data.get("title"),
                    author=pr_data.get("user", {}).get("login"),
                    base_branch=pr_data.get("base", {}).get("ref"),
                    head_branch=pr_data.get("head", {}).get("ref"),
                    head_sha=pr_data.get("head", {}).get("sha"),
                    installation_id=installation.get("id"),
                    webhook_delivery_id=x_github_delivery
                )
                
                # Create task and enqueue
                task = PRTask(pr_metadata=pr_metadata)
                success = await queue.enqueue(task)
                
                if success:
                    logger.info(
                        "PR task enqueued",
                        pr_id=pr_metadata.pr_id,
                        repository=pr_metadata.repository,
                        action=action
                    )
                    return {
                        "status": "queued",
                        "message": f"PR #{pr_metadata.pr_id} queued for review",
                        "pr_id": str(pr_metadata.pr_id)
                    }
                else:
                    logger.error("Failed to enqueue PR task", pr_id=pr_metadata.pr_id)
                    raise HTTPException(status_code=500, detail="Failed to queue PR for review")
            else:
                logger.info("Ignoring PR action", action=action)
                return {"status": "ignored", "message": f"Action '{action}' not processed"}
        
        # Handle ping event (GitHub App installation)
        elif event_type == "ping":
            logger.info("GitHub App ping received", delivery_id=x_github_delivery)
            return {"status": "ok", "message": "Webhook is working"}
        
        else:
            logger.info("Unhandled event type", event_type=event_type)
            return {"status": "ignored", "message": f"Event type '{event_type}' not handled"}
    
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in webhook payload", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    except Exception as e:
        logger.error("Webhook handling error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")

