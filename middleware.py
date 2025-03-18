"""
Middleware for tracking file descriptor usage in a FastAPI application.
"""

import uuid
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse

from fd_monitor import get_fd_limit, get_open_fd_count, fd_monitor

# Configure logging
logger = logging.getLogger(__name__)

class ResourceMonitorMiddleware(BaseHTTPMiddleware):
    """Middleware to monitor resource usage, particularly file descriptors."""
    
    def __init__(self, app, alert_threshold: float = 0.8):
        """
        Initialize the middleware.
        
        Args:
            app: The FastAPI application
            alert_threshold: Threshold (0.0-1.0) of FD limit to trigger alerts
        """
        super().__init__(app)
        self.alert_threshold = alert_threshold
        
        # Log initial state
        soft_limit, hard_limit = get_fd_limit()
        fd_count, (files, sockets) = get_open_fd_count()
        
        if soft_limit:
            logger.info(
                f"ResourceMonitorMiddleware initialized. FD usage: {fd_count}/{soft_limit} "
                f"({fd_count/soft_limit:.1%})"
            )
        else:
            logger.info(
                f"ResourceMonitorMiddleware initialized. FD count: {fd_count} (limit unknown)"
            )
    
    async def dispatch(self, request: Request, call_next):
        """Process the request, checking resource usage."""
        # Generate a unique request ID
        request_id = str(uuid.uuid4())[:8]
        
        # Get current FD count
        soft_limit, _ = get_fd_limit()
        fd_count, _ = get_open_fd_count()
        
        # Check if we're approaching the limit
        if soft_limit and fd_count > soft_limit * self.alert_threshold:
            logger.warning(
                f"Request {request_id}: High FD usage before processing: "
                f"{fd_count}/{soft_limit} ({fd_count/soft_limit:.1%})"
            )
            
            # If we're very close to the limit, return an error
            if fd_count > soft_limit * 0.95:
                logger.critical(
                    f"Request {request_id}: FD usage critical: "
                    f"{fd_count}/{soft_limit} ({fd_count/soft_limit:.1%})"
                )
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "Server is experiencing high load. Please try again later.",
                        "type": "resource_exhaustion"
                    }
                )
        
        # Monitor FD usage during request processing
        try:
            with fd_monitor(f"request {request_id} to {request.url.path}", self.alert_threshold):
                response = await call_next(request)
                return response
        except Exception as e:
            # Handle unhandled exceptions
            logger.exception(f"Unhandled error in request {request_id}: {str(e)}")
            
            # Check if it might be due to FD exhaustion
            if "Too many open files" in str(e):
                logger.critical(f"File descriptor limit reached: {str(e)}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "detail": "Server encountered a resource limit. Please try again later.",
                        "type": "file_descriptor_limit"
                    }
                )
            
            # Return a generic error
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"}
            ) 