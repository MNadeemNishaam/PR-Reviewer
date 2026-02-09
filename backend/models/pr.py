from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class PRMetadata(BaseModel):
    pr_id: int = Field(..., description="GitHub PR number")
    repository: str = Field(..., description="Repository full name (owner/repo)")
    owner: str = Field(..., description="Repository owner")
    repo_name: str = Field(..., description="Repository name")
    title: str = Field(..., description="PR title")
    author: str = Field(..., description="PR author username")
    base_branch: str = Field(..., description="Base branch name")
    head_branch: str = Field(..., description="Head branch name")
    head_sha: str = Field(..., description="Head commit SHA")
    installation_id: int = Field(..., description="GitHub App installation ID")
    webhook_delivery_id: Optional[str] = Field(None, description="GitHub webhook delivery ID")


class PRTask(BaseModel):
    pr_metadata: PRMetadata
    queued_at: datetime = Field(default_factory=datetime.utcnow)
    retry_count: int = 0


class PRReviewStatus(BaseModel):
    pr_id: int
    repository: str
    status: str = Field(..., description="pending, processing, completed, failed")
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    comment_posted: bool = False
    comment_id: Optional[int] = None

