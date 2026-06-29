"""
API Gateway
A thin routing/middleware layer in front of an APIManager. Middleware can
transform or reject requests (auth, logging, parameter injection) before the
underlying APIManager.make_request runs, and transform responses afterward.
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from .api_manager import APIManager, APIResponse

# A request middleware takes (endpoint_name, params) and returns possibly-modified
# params, or raises to reject the request.
RequestMiddleware = Callable[[str, Dict[str, Any]], Dict[str, Any]]
# A response middleware takes an APIResponse and returns a (possibly new) APIResponse.
ResponseMiddleware = Callable[[APIResponse], APIResponse]


class APIGateway:
    """Route requests through middleware to a backing APIManager."""

    def __init__(self, api_manager: Optional[APIManager] = None):
        self.logger = logging.getLogger(__name__)
        self.api_manager = api_manager or APIManager()
        self.request_middleware: List[RequestMiddleware] = []
        self.response_middleware: List[ResponseMiddleware] = []
        # Per-endpoint gateway-level rate-limit overrides (req/min).
        self.rate_overrides: Dict[str, int] = {}

    def add_middleware(self, fn: RequestMiddleware):
        """Add a request middleware (runs in registration order before the request)."""
        self.request_middleware.append(fn)
        self.logger.info("Added request middleware")

    def add_response_middleware(self, fn: ResponseMiddleware):
        """Add a response middleware (runs in registration order after the request)."""
        self.response_middleware.append(fn)
        self.logger.info("Added response middleware")

    def add_rate_limit(self, endpoint_name: str, limit: int):
        """Override the rate limit for an endpoint at the gateway level."""
        self.rate_overrides[endpoint_name] = limit
        if endpoint_name in self.api_manager.endpoints:
            self.api_manager.endpoints[endpoint_name].rate_limit = limit
        self.logger.info(f"Rate limit for {endpoint_name} set to {limit} req/min")

    def route(self, endpoint_name: str, params: Optional[Dict[str, Any]] = None,
              use_cache: bool = True) -> Optional[APIResponse]:
        """Route a request through middleware to the APIManager.

        Returns None if a middleware rejects the request or the underlying
        request fails.
        """
        params = dict(params or {})

        # Apply request middleware in order; any raise rejects the request.
        for mw in self.request_middleware:
            try:
                params = mw(endpoint_name, params)
            except Exception as e:
                self.logger.warning(f"Request rejected by middleware: {e}")
                return None

        response = self.api_manager.make_request(
            endpoint_name, params=params, use_cache=use_cache
        )
        if response is None:
            return None

        # Apply response middleware in order.
        for mw in self.response_middleware:
            try:
                response = mw(response)
            except Exception as e:
                self.logger.warning(f"Response middleware error: {e}")
        return response

    def register_endpoint(self, name, endpoint):
        """Convenience pass-through to the backing APIManager."""
        self.api_manager.register_endpoint(name, endpoint)
        if name in self.rate_overrides:
            endpoint.rate_limit = self.rate_overrides[name]
