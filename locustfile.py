"""
Locust load test file for testing file descriptor exhaustion in Uvicorn
Run with: locust -f locustfile.py --host http://localhost
"""

import time
import random
from locust import HttpUser, task, between

class FileDescriptorExhaustUser(HttpUser):
    """
    User that creates file descriptor leaks to demonstrate
    how they can cause 502 errors in Uvicorn behind Nginx
    """
    wait_time = between(0.5, 1.5)  # Wait between requests
    
    def on_start(self):
        """Check initial resource state"""
        self.client.get("/")

    @task(10)
    def create_leak(self):
        """Create a file descriptor leak"""
        # Leak 1-3 file descriptors at a time
        count = random.randint(1, 3)
        self.client.post(f"/leak?count={count}")
    
    @task(5)
    def check_status(self):
        """Check current status"""
        self.client.get("/")
    
    @task(1)
    def cleanup(self):
        """Occasionally clean up (to avoid complete failure)"""
        # Only clean up 20% of the time
        if random.random() < 0.2:
            self.client.post("/cleanup") 