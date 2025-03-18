"""
Simple FastAPI app to demonstrate file descriptor exhaustion.

This app has endpoints that:
1. Show current file descriptor usage
2. Create file descriptor leaks on demand
3. Clean up leaked file descriptors
"""

import os
import gc
import time
import logging
import tempfile
from typing import List, Dict, Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

# Import our middleware for monitoring file descriptor usage
from middleware import ResourceMonitorMiddleware
from fd_monitor import get_fd_limit, get_open_fd_count

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Create the FastAPI application
app = FastAPI(title="File Descriptor Monitor Demo")

# Add the resource monitoring middleware
# Comment out to disable middleware and allow FD exhaustion to demonstrate 502 errors
#app.add_middleware(ResourceMonitorMiddleware)

# Global storage for tracking leaked file descriptors
leaked_files = []

# Define response models
class ResourceInfo(BaseModel):
    """Resource information"""
    fd_count: int
    fd_limit_soft: Optional[int] = None
    fd_limit_hard: Optional[int] = None
    open_files: int
    open_connections: int
    pct_of_limit: Optional[float] = None
    leaked_files_count: int

@app.get("/", response_model=ResourceInfo)
async def get_resource_info():
    """Get current resource information"""
    fd_count, (files, connections) = get_open_fd_count()
    soft_limit, hard_limit = get_fd_limit()
    
    return ResourceInfo(
        fd_count=fd_count,
        fd_limit_soft=soft_limit,
        fd_limit_hard=hard_limit,
        open_files=files,
        open_connections=connections,
        pct_of_limit=fd_count/soft_limit if soft_limit else None,
        leaked_files_count=len(leaked_files)
    )

@app.post("/leak")
async def create_fd_leak(count: int = 10, cleanup_after: int = 0, background_tasks: BackgroundTasks = None):
    """
    Create file descriptor leaks by opening files and not closing them.
    
    Args:
        count: Number of file descriptors to leak
        cleanup_after: Seconds after which to clean up (0 = never)
    """
    global leaked_files
    
    # Check if we're already near limit
    fd_count, _ = get_open_fd_count()
    soft_limit, _ = get_fd_limit()
    
    if soft_limit and fd_count > soft_limit * 0.98:
        raise HTTPException(
            status_code=429,
            detail=f"Already too close to FD limit: {fd_count}/{soft_limit}"
        )
    
    # Create temporary files that remain open
    new_leaks = []
    for i in range(count):
        try:
            # Create and keep a file handle open
            temp = tempfile.TemporaryFile()
            temp.write(b"This is a leaked file descriptor")
            
            # Don't close it - that's the leak
            new_leaks.append(temp)
            
            # Log every 10 files
            if (i + 1) % 10 == 0 or i == 0:
                logging.info(f"Created {i+1} leaked file descriptors")
        except Exception as e:
            logging.error(f"Failed to create temporary file: {e}")
            break
    
    # Add to our global list
    leaked_files.extend(new_leaks)
    
    # Schedule cleanup if requested
    if cleanup_after > 0 and background_tasks:
        background_tasks.add_task(cleanup_leaked_fds, len(new_leaks), cleanup_after)
    
    return {
        "message": f"Created {len(new_leaks)} leaked file descriptors",
        "total_leaked": len(leaked_files)
    }

@app.post("/cleanup")
async def cleanup_leaks():
    """Clean up all leaked file descriptors"""
    global leaked_files
    count = len(leaked_files)
    
    for temp in leaked_files:
        try:
            temp.close()
        except Exception as e:
            logging.error(f"Error closing file: {e}")
    
    # Clear the list
    leaked_files.clear()
    
    # Force garbage collection
    gc.collect()
    
    # Get updated resource information
    fd_count, _ = get_open_fd_count()
    soft_limit, _ = get_fd_limit()
    
    return {
        "message": f"Cleaned up {count} leaked file descriptors",
        "current_fd_count": fd_count,
        "pct_of_limit": fd_count/soft_limit if soft_limit else None
    }

def cleanup_leaked_fds(count, delay):
    """Background task to clean up leaked file descriptors after a delay"""
    global leaked_files
    
    logging.info(f"Scheduled cleanup of {count} file descriptors in {delay} seconds")
    
    # Wait for specified delay
    time.sleep(delay)
    
    # Close the specified number of files
    to_close = min(count, len(leaked_files))
    for _ in range(to_close):
        try:
            if leaked_files:
                temp = leaked_files.pop()
                temp.close()
        except Exception as e:
            logging.error(f"Error closing temporary file: {e}")
    
    logging.info(f"Background cleanup: closed {to_close} temporary files")

@app.get("/error")
async def force_error():
    """Deliberately cause an error to test error handling"""
    1/0  # Division by zero error

if __name__ == "__main__":
    # Reduce file descriptor limit for testing
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        # Set a low soft limit (100) for demonstration purposes
        new_soft = min(soft, 100)
        resource.setrlimit(resource.RLIMIT_NOFILE, (new_soft, hard))
        print(f"Reduced file descriptor limit to {new_soft} for demonstration")
    except (ImportError, AttributeError, PermissionError) as e:
        print(f"Could not set file descriptor limit: {e}")
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info") 