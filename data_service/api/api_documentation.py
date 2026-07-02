"""
API Documentation
Introspects an APIManager's registered endpoints and renders documentation as
Markdown or an OpenAPI 3.0 specification.
"""

import json
import logging
from typing import Any, Dict

from .api_manager import APIManager


class APIDocumentation:
    """Generate human- and machine-readable docs from registered endpoints."""

    def __init__(self, api_manager: APIManager, title: str = "Trading System API",
                 version: str = "1.0.0"):
        self.logger = logging.getLogger(__name__)
        self.api_manager = api_manager
        self.title = title
        self.version = version

    def generate_markdown(self) -> str:
        """Render all registered endpoints as a Markdown document."""
        lines = [f"# {self.title}", "", f"Version: {self.version}", ""]
        if not self.api_manager.endpoints:
            lines.append("_No endpoints registered._")
            return "\n".join(lines)

        lines.append(f"{len(self.api_manager.endpoints)} endpoint(s) registered.")
        lines.append("")
        for name, ep in sorted(self.api_manager.endpoints.items()):
            lines.append(f"## `{name}`")
            lines.append("")
            lines.append(f"- **URL**: `{ep.url}`")
            lines.append(f"- **Method**: `{ep.method.upper()}`")
            lines.append(f"- **Rate limit**: {ep.rate_limit} req/min")
            lines.append(f"- **Timeout**: {ep.timeout}s")
            lines.append(f"- **Retries**: {ep.retry_count} (delay {ep.retry_delay}s)")
            if ep.params:
                lines.append("- **Default params**:")
                for k, v in ep.params.items():
                    lines.append(f"  - `{k}`: `{v}`")
            if ep.headers:
                # Don't leak secrets — list header names only.
                lines.append(f"- **Headers**: {', '.join(ep.headers.keys())}")
            lines.append("")
        return "\n".join(lines)

    def generate_openapi(self) -> Dict[str, Any]:
        """Render a minimal OpenAPI 3.0 spec describing the endpoints."""
        paths: Dict[str, Any] = {}
        for name, ep in self.api_manager.endpoints.items():
            method = ep.method.lower()
            params = [
                {"name": k, "in": "query", "required": False,
                 "schema": {"type": "string"}, "example": v}
                for k, v in (ep.params or {}).items()
            ]
            operation = {
                "operationId": name,
                "summary": f"{name} endpoint",
                "responses": {"200": {"description": "Successful response"}},
            }
            if method == "get" and params:
                operation["parameters"] = params
            # Use the endpoint url as the path key so distinct endpoints don't collide.
            paths[ep.url] = {**paths.get(ep.url, {}), method: operation}

        return {
            "openapi": "3.0.0",
            "info": {"title": self.title, "version": self.version},
            "paths": paths,
        }

    def export(self, filepath: str, format: str = "markdown") -> bool:
        """Write the documentation to disk. format is 'markdown' or 'openapi'."""
        try:
            if format == "markdown":
                content = self.generate_markdown()
            elif format == "openapi":
                content = json.dumps(self.generate_openapi(), indent=2)
            else:
                raise ValueError(f"Unknown format: {format}")
            with open(filepath, "w") as f:
                f.write(content)
            self.logger.info(f"API documentation ({format}) written to {filepath}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to export documentation: {e}")
            return False
