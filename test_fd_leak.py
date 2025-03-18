#!/usr/bin/env python3
"""
Simple script to test file descriptor exhaustion in Uvicorn
This script creates FD leaks in batches and monitors for 502 errors
"""

import time
import requests
import sys

# Config
NGINX_URL = "http://localhost"
DIRECT_URL = "http://localhost:8000"
BATCH_SIZE = 5  # How many file descriptors to leak in each request
MAX_REQUESTS = 1000  # Maximum number of requests to send

def get_resource_info():
    """Get the current resource information from the server"""
    try:
        response = requests.get(f"{DIRECT_URL}/")
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error getting resource info: {response.status_code}")
            return {}
    except Exception as e:
        print(f"Exception getting resource info: {e}")
        return {}

def cleanup():
    """Clean up leaked file descriptors"""
    print("\nCleaning up leaked file descriptors...")
    try:
        response = requests.post(f"{DIRECT_URL}/cleanup")
        if response.status_code == 200:
            print("Cleanup successful")
            result = response.json()
            print(f"Cleaned up {result.get('message', 'unknown')}")
            print(f"Current FD count: {result.get('current_fd_count', 'N/A')}")
        else:
            print(f"Cleanup failed with status code: {response.status_code}")
    except Exception as e:
        print(f"Cleanup exception: {e}")

def test_with_increasing_load():
    """Test with progressively increasing load until we see 502 errors"""
    print("\nTesting with progressively increasing load...")
    
    # Start with a clean slate
    cleanup()
    
    # Get initial resource info
    initial_info = get_resource_info()
    fd_limit = initial_info.get('fd_limit_soft', 'unknown')
    print(f"Initial FD count: {initial_info.get('fd_count', 'N/A')}/{fd_limit}")
    
    # Track results
    success_count = 0
    nginx_502_count = 0
    other_failures = 0
    total_leaks = 0
    
    # Start time for rate calculation
    start_time = time.time()
    
    print("Sending requests to create file descriptor leaks...")
    print("Will stop after hitting 502 errors or reaching max requests")
    
    for i in range(MAX_REQUESTS):
        try:
            # Create file descriptor leak through Nginx
            response = requests.post(f"{NGINX_URL}/leak", params={"count": BATCH_SIZE})
            
            # Check response
            if response.status_code == 200:
                success_count += 1
                total_leaks += BATCH_SIZE
            elif response.status_code == 502:
                nginx_502_count += 1
                print(f"🔴 Received 502 Bad Gateway (total: {nginx_502_count})")
            else:
                other_failures += 1
                print(f"⚠️ Unexpected status code: {response.status_code}")
            
            # Get current stats every 10 requests
            if (i + 1) % 10 == 0 or nginx_502_count == 1 or nginx_502_count % 5 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                
                current_info = get_resource_info()
                fd_count = current_info.get('fd_count', 'N/A')
                leaked_files = current_info.get('leaked_files_count', 'N/A')
                
                # Print current status
                print(f"\nProgress: {i+1} requests in {elapsed:.1f}s ({rate:.1f}/s)")
                print(f"  Success: {success_count}, 502 Errors: {nginx_502_count}, Other Failures: {other_failures}")
                print(f"  File Descriptors: {fd_count}/{fd_limit}")
                print(f"  Leaked files: {leaked_files}")
                
                # If we've seen multiple 502 errors, we've proven our point
                if nginx_502_count >= 10:
                    print("Reached 10+ 502 errors, stopping test.")
                    break
            
            # Simple progress indicator
            if (i + 1) % 10 == 0:
                sys.stdout.write(".")
                sys.stdout.flush()
                
        except Exception as e:
            # Handle connection errors
            other_failures += 1
            print(f"\nRequest failed: {e}")
            time.sleep(0.5)  # Brief pause after errors
    
    # Calculate and print test summary
    total_time = time.time() - start_time
    total_requests = success_count + nginx_502_count + other_failures
    req_per_sec = total_requests / total_time if total_time > 0 else 0
    
    print(f"\nTest completed in {total_time:.1f} seconds")
    print(f"Total requests: {total_requests}")
    print(f"Successful requests: {success_count}")
    print(f"502 errors: {nginx_502_count}")
    print(f"Other failures: {other_failures}")
    print(f"Average rate: {req_per_sec:.1f} requests/second")
    
    # Get final resource info
    final_info = get_resource_info()
    print(f"Final FD count: {final_info.get('fd_count', 'N/A')}/{fd_limit}")
    print(f"Total leaked files: {final_info.get('leaked_files_count', 'N/A')}")
    
    return success_count, nginx_502_count, other_failures

def main():
    print("File Descriptor Exhaustion Test")
    print("===============================")
    print(f"Will create file descriptor leaks in batches of {BATCH_SIZE}")
    print(f"Maximum requests: {MAX_REQUESTS}")
    
    try:
        # Run the test
        success, nginx_502, other = test_with_increasing_load()
        
        # Clean up after test
        cleanup()
        
        # Summary
        print("\nTest Summary")
        print("===========")
        if nginx_502 > 0:
            print("✅ CONFIRMED: File descriptor exhaustion caused 502 errors through Nginx")
            print(f"Total 502 errors: {nginx_502}")
        else:
            print("❌ NOT CONFIRMED: No 502 errors were observed. Try increasing batch size.")
    
    except KeyboardInterrupt:
        print("\nTest interrupted. Cleaning up...")
        cleanup()
    except Exception as e:
        print(f"\nTest failed with exception: {e}")
        cleanup()

if __name__ == "__main__":
    main() 