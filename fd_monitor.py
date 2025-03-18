"""
File descriptor monitoring utility.

Tracks file descriptor usage to diagnose 502 errors in FastAPI/Uvicorn applications.
"""

import os
import time
import logging
import contextlib
from typing import Dict, Tuple, Optional, Any

# If psutil is available, use it for more accurate FD counting
try:
    import psutil
    HAVE_PSUTIL = True
except ImportError:
    HAVE_PSUTIL = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_fd_limit() -> Tuple[Optional[int], Optional[int]]:
    """Get the soft and hard limit for file descriptors"""
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        return soft, hard
    except (ImportError, AttributeError):
        # Windows or other platform without resource module
        return None, None

def get_open_fd_count() -> Tuple[int, Tuple[int, int]]:
    """
    Get the count of open file descriptors.
    
    Returns:
        Tuple of (total_count, (file_count, socket_count))
    """
    if HAVE_PSUTIL:
        try:
            proc = psutil.Process()
            file_count = 0
            socket_count = 0
            
            # Count connections
            for conn in proc.connections(kind='all'):
                if hasattr(conn, 'type') and conn.type == socket:
                    socket_count += 1
                else:
                    file_count += 1
            
            # Get open files
            open_files = proc.open_files()
            file_count += len(open_files)
            
            total = file_count + socket_count
            return total, (file_count, socket_count)
        except Exception as e:
            logger.warning(f"Error using psutil to count FDs: {e}")
            # Fall back to /proc method
            pass
    
    # Fall back to counting entries in /proc/self/fd on Linux
    try:
        fd_dir = '/proc/self/fd'
        if os.path.isdir(fd_dir):
            # Count all file descriptors in the directory
            count = len(os.listdir(fd_dir))
            # Subtract 1 because the act of listing the directory opens a file descriptor
            return max(0, count - 1), (count - 1, 0)
    except Exception as e:
        logger.warning(f"Error counting FDs from /proc: {e}")
    
    # Fall back to a less accurate method
    # This will typically undercount as it only sees FDs in the current process
    try:
        # Get the highest available FD by trying to dup until failure
        for i in range(1000):  # Try a reasonable number
            try:
                fd = os.dup(1)  # Duplicate stdout
                os.close(fd)  # Close immediately
            except OSError:
                return i, (i, 0)
    except Exception as e:
        logger.warning(f"Error estimating FDs using dup: {e}")
    
    # If all methods fail, return a safe value
    logger.warning("Could not determine open file descriptor count, returning estimate")
    return 50, (50, 0)  # Return a reasonable guess

@contextlib.contextmanager
def fd_monitor(context_name: str = "operation", alert_threshold: float = 0.8):
    """
    Context manager to monitor file descriptor usage before and after a code block.
    
    Args:
        context_name: Name of the context for logging
        alert_threshold: Threshold (0.0-1.0) of FD limit to trigger alerts
    """
    start_time = time.time()
    
    # Get initial FD count and limits
    soft_limit, hard_limit = get_fd_limit()
    initial_count, (initial_files, initial_sockets) = get_open_fd_count()
    
    initial_pct = None
    if soft_limit:
        initial_pct = initial_count / soft_limit
        if initial_pct > alert_threshold:
            logger.warning(
                f"FD usage before {context_name}: {initial_count}/{soft_limit} "
                f"({initial_pct:.1%}) - approaching limit!"
            )
        else:
            logger.info(
                f"FD usage before {context_name}: {initial_count}/{soft_limit} "
                f"({initial_pct:.1%})"
            )
    else:
        logger.info(f"FD count before {context_name}: {initial_count} (limit unknown)")
    
    try:
        # Execute the code block
        yield
    finally:
        # Calculate duration
        duration = time.time() - start_time
        
        # Get final FD counts
        final_count, (final_files, final_sockets) = get_open_fd_count()
        diff = final_count - initial_count
        
        # Log results
        if diff != 0:
            if diff > 0:
                leak_msg = f"Potential FD leak: +{diff} FDs"
                logger.warning(leak_msg)
            else:
                logger.info(f"FD change: {diff} FDs")
        
        if soft_limit:
            final_pct = final_count / soft_limit
            logger.info(
                f"FD usage after {context_name}: {final_count}/{soft_limit} "
                f"({final_pct:.1%}) in {duration:.2f}s"
            )
            
            if final_pct > alert_threshold:
                logger.warning(
                    f"FD usage is high: {final_count}/{soft_limit} ({final_pct:.1%})"
                )
        else:
            logger.info(
                f"FD count after {context_name}: {final_count} (limit unknown) "
                f"in {duration:.2f}s"
            ) 