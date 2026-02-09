import time
import jwt
import httpx
import structlog
from typing import Optional, Dict, Any
from backend.config.settings import settings

logger = structlog.get_logger(__name__)


class GitHubClient:
    
    def __init__(self):
        self.base_url = "https://api.github.com"
        self.app_id = settings.github_app_id
        self.private_key = settings.get_github_private_key()
        self._installation_tokens: Dict[int, tuple] = {}  # installation_id -> (token, expires_at)
    
    def _generate_jwt(self) -> str:
        now = int(time.time())
        payload = {
            "iat": now - 60,  # Issued at time (1 minute ago to account for clock skew)
            "exp": now + 600,  # Expires in 10 minutes
            "iss": self.app_id  # Issuer (App ID)
        }
        
        token = jwt.encode(payload, self.private_key, algorithm="RS256")
        return token
    
    async def _get_installation_token(self, installation_id: int) -> str:
        # Check if we have a valid cached token
        if installation_id in self._installation_tokens:
            token, expires_at = self._installation_tokens[installation_id]
            if time.time() < expires_at - 60:  # Refresh 1 minute before expiry
                return token
        
        # Generate new token
        jwt_token = self._generate_jwt()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/app/installations/{installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {jwt_token}",
                    "Accept": "application/vnd.github.v3+json"
                },
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()
            token = data["token"]
            expires_at = time.time() + data["expires_at"] - time.time() - 60  # Subtract 1 minute buffer
            
            self._installation_tokens[installation_id] = (token, expires_at)
            logger.info("Generated new installation token", installation_id=installation_id)
            return token
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        installation_id: int,
        **kwargs
    ) -> httpx.Response:
        token = await self._get_installation_token(installation_id)
        url = f"{self.base_url}{endpoint}"
        
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "PR-Reviewer/1.0"
        }
        
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            return response
    
    async def get_pr_diff(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        installation_id: int
    ) -> str:
        try:
            endpoint = f"/repos/{owner}/{repo}/pulls/{pr_number}"
            response = await self._make_request("GET", endpoint, installation_id)
            pr_data = response.json()
            
            # Get the diff
            diff_endpoint = f"/repos/{owner}/{repo}/pulls/{pr_number}"
            diff_response = await self._make_request(
                "GET",
                diff_endpoint,
                installation_id,
                headers={"Accept": "application/vnd.github.v3.diff"}
            )
            
            diff = diff_response.text
            logger.info("Fetched PR diff", owner=owner, repo=repo, pr_number=pr_number, diff_size=len(diff))
            return diff
        except httpx.HTTPStatusError as e:
            logger.error("Failed to fetch PR diff", error=str(e), status_code=e.response.status_code)
            raise
        except Exception as e:
            logger.error("Error fetching PR diff", error=str(e))
            raise
    
    async def get_pr_files(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        installation_id: int
    ) -> list[Dict[str, Any]]:
        try:
            endpoint = f"/repos/{owner}/{repo}/pulls/{pr_number}/files"
            response = await self._make_request("GET", endpoint, installation_id)
            files = response.json()
            return files
        except Exception as e:
            logger.error("Error fetching PR files", error=str(e))
            raise
    
    async def post_pr_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        installation_id: int,
        body: str
    ) -> Dict[str, Any]:
        try:
            endpoint = f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
            payload = {
                "body": body,
                "event": "COMMENT"  # Just a comment, not approve/reject
            }
            
            response = await self._make_request("POST", endpoint, installation_id, json=payload)
            comment_data = response.json()
            logger.info("Posted PR comment", owner=owner, repo=repo, pr_number=pr_number, comment_id=comment_data.get("id"))
            return comment_data
        except httpx.HTTPStatusError as e:
            # Try alternative endpoint for comments
            try:
                endpoint = f"/repos/{owner}/{repo}/issues/{pr_number}/comments"
                payload = {"body": body}
                response = await self._make_request("POST", endpoint, installation_id, json=payload)
                comment_data = response.json()
                logger.info("Posted PR comment (via issues endpoint)", owner=owner, repo=repo, pr_number=pr_number)
                return comment_data
            except Exception as e2:
                logger.error("Failed to post PR comment", error=str(e2))
                raise
        except Exception as e:
            logger.error("Error posting PR comment", error=str(e))
            raise
    
    async def get_pr_details(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        installation_id: int
    ) -> Dict[str, Any]:
        try:
            endpoint = f"/repos/{owner}/{repo}/pulls/{pr_number}"
            response = await self._make_request("GET", endpoint, installation_id)
            return response.json()
        except Exception as e:
            logger.error("Error fetching PR details", error=str(e))
            raise


# Global GitHub client instance
github_client = GitHubClient()

