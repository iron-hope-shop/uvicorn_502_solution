# Uvicorn 502 Error Demo: File Descriptor Exhaustion

This repository demonstrates and explains how file descriptor exhaustion in FastAPI/Uvicorn applications can lead to 502 Bad Gateway errors when served behind Nginx.

## Problem Overview

When a FastAPI application served by Uvicorn runs out of file descriptors, it can no longer accept new connections or open files. This situation manifests as 502 Bad Gateway errors when the application is behind Nginx or another reverse proxy, which can be confusing to diagnose.

## What are File Descriptors?

File descriptors (FDs) are numeric identifiers for open files, sockets, and other I/O resources in UNIX-like systems. Each connection to your application uses at least one file descriptor, and there's a system-defined limit to how many a process can have open simultaneously.

When an application exhausts its available file descriptors:
1. It can't accept new network connections
2. It can't open new files
3. Any proxies (like Nginx) that attempt to connect receive connection failures
4. These connection failures manifest as 502 Bad Gateway errors

## Repository Contents

This repository provides a complete environment to demonstrate and debug this issue:

- `app.py`: FastAPI application with endpoints to:
  - Show current file descriptor usage
  - Create controlled file descriptor leaks
  - Clean up leaked file descriptors
- `middleware.py`: FastAPI middleware that prevents complete exhaustion by monitoring FD usage
- `fd_monitor.py`: Utility functions for monitoring and reporting file descriptor usage
- `simple_test.py`: Simple script to demonstrate 502 errors by incrementally leaking FDs
- `test_fd_leak.py`: More detailed test script with better reporting
- `nginx.conf`: Nginx configuration for proxying to the FastAPI app
- `docker-compose.yml`: Docker setup with controlled FD limits for demonstration
- `Dockerfile`: Application container with necessary dependencies

## How to Run the Demo

### Prerequisites

- Docker and Docker Compose

### Setup

1. Clone this repository:
   ```bash
   git clone https://github.com/iron-hope-shop/uvicorn_502_solution.git
   cd uvicorn_502_solution
   ```

2. Start the Docker containers:
   ```bash
   docker-compose up -d
   ```

3. Verify the application is running:
   ```bash
   curl http://localhost/
   curl http://localhost:8000/
   ```

### Running the Tests

1. Run the simple test script to demonstrate 502 errors:
   ```bash
   python3 simple_test.py
   ```

2. For more detailed testing:
   ```bash
   python3 test_fd_leak.py
   ```

## Understanding the Results

When running the tests, you'll observe:
1. Initially, all requests succeed
2. As file descriptors are leaked, you'll start to see warnings in the logs
3. Once the application approaches its file descriptor limit (50 in our demo), it will become unresponsive
4. Nginx will start returning 502 Bad Gateway errors

## How to Fix File Descriptor Exhaustion

### 1. Increase File Descriptor Limits

In production environments, configure higher limits:

**For systemd services:**
```ini
# /etc/systemd/system/your-service.service
[Service]
LimitNOFILE=65535
```

**For Docker containers:**
```yaml
# docker-compose.yml
services:
  app:
    ulimits:
      nofile:
        soft: 65535
        hard: 65535
```

**For Linux systems:**
```bash
# /etc/security/limits.conf
your_user soft nofile 65535
your_user hard nofile 65535
```

### 2. Implement Protective Middleware

This repository includes a `ResourceMonitorMiddleware` in `middleware.py` that:
- Monitors file descriptor usage before processing each request
- Returns a 503 Service Unavailable when approaching limits (95%)
- Properly logs usage patterns for easier diagnosis

To enable it, uncomment this line in `app.py`:
```python
app.add_middleware(ResourceMonitorMiddleware)
```

### 3. Fix Resource Leaks

Make sure your application properly closes all resources:

```python
# BAD - resource leak
def bad_function():
    f = open("file.txt", "r")
    data = f.read()
    return data  # File never closed!

# GOOD - using context manager
def good_function():
    with open("file.txt", "r") as f:
        data = f.read()
    return data  # File automatically closed
```

### 4. Use Connection Pooling

Properly configure connection pools for databases and external services:

```python
from sqlalchemy import create_engine

# Configure pool size appropriately
DATABASE_URL = "postgresql://user:password@localhost/dbname"
engine = create_engine(
    DATABASE_URL,
    pool_size=5,        # Base number of connections to keep
    max_overflow=10     # Maximum additional connections to create
)
```

### 5. Set Appropriate Timeouts

Configure timeouts in both Uvicorn and Nginx:

**Uvicorn:**
```bash
uvicorn app:app --timeout-keep-alive 5
```

**Nginx:**
```nginx
# Lower the keepalive timeout
keepalive_timeout 65;

# Set shorter timeouts for the upstream
proxy_connect_timeout 5s;
proxy_read_timeout 10s;
proxy_send_timeout 10s;
```

## Debugging File Descriptor Issues

### Checking File Descriptor Usage

```bash
# For a specific PID
lsof -p <pid> | wc -l

# Check system limits
ulimit -n

# On Linux
cat /proc/sys/fs/file-max
```

### Monitoring in Production

Use the included `fd_monitor.py` utilities to add monitoring to your application.

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. 