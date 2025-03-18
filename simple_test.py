#!/usr/bin/env python3
"""
Very simple script to test file descriptor exhaustion causing 502 errors.
This script leaks file descriptors one at a time until 502 errors occur.
"""

import time
import requests
import sys

# Number of file descriptors to leak per request
FD_LEAK_COUNT = 3

# Maximum number of requests to make
MAX_REQUESTS = 100

def main():
    print("Simple FD Exhaustion Test")
    print("========================")
    print(f"Leaking {FD_LEAK_COUNT} file descriptor(s) per request")
    print(f"Press Ctrl+C to stop at any time")
    print("")
    
    # Track results
    successful = 0
    errors = 0
    error_502 = 0
    
    # Get initial FD info
    try:
        r = requests.get("http://localhost:8000/")
        if r.status_code == 200:
            data = r.json()
            print(f"Initial FD count: {data.get('fd_count')}/{data.get('fd_limit_soft')}")
        else:
            print(f"Failed to get initial FD count: {r.status_code}")
    except Exception as e:
        print(f"Error getting initial info: {e}")
    
    print("\nMaking requests to Nginx (http://localhost)...")
    
    try:
        for i in range(1, MAX_REQUESTS + 1):
            # Request to create FD leak through Nginx
            try:
                start = time.time()
                r = requests.post(f"http://localhost/leak?count={FD_LEAK_COUNT}", timeout=10)
                elapsed = time.time() - start
                
                if r.status_code == 200:
                    successful += 1
                    status = "✅ OK"
                elif r.status_code == 502:
                    error_502 += 1
                    status = "⛔ 502 BAD GATEWAY"
                else:
                    errors += 1
                    status = f"❌ ERROR {r.status_code}"
                
                # Also check direct app status
                try:
                    app_r = requests.get("http://localhost:8000/", timeout=5)
                    if app_r.status_code == 200:
                        app_data = app_r.json()
                        fd_count = app_data.get('fd_count')
                        fd_limit = app_data.get('fd_limit_soft')
                        fd_pct = round(fd_count/fd_limit*100) if fd_limit else 0
                        leaked = app_data.get('leaked_files_count')
                        app_status = f"FDs: {fd_count}/{fd_limit} ({fd_pct}%), Leaked: {leaked}"
                    else:
                        app_status = f"App status: {app_r.status_code}"
                except Exception as app_e:
                    app_status = f"App error: {str(app_e)[:40]}..."
                
                # Print status line with counts and time
                print(f"[{i:3d}] {status} ({elapsed:.2f}s) - {app_status}")
                
                # If we've hit 10 502 errors, we've proven the point
                if error_502 >= 10:
                    print("Reached 10 502 errors, test complete!")
                    break
                    
                # Brief pause between requests
                time.sleep(0.1)
                
            except Exception as e:
                errors += 1
                print(f"[{i:3d}] ❌ EXCEPTION: {str(e)[:60]}...")
                time.sleep(1)  # Longer pause after error
    
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
    
    # Print summary
    print("\nTest Summary")
    print("===========")
    print(f"Successful requests: {successful}")
    print(f"502 Bad Gateway errors: {error_502}")
    print(f"Other errors: {errors}")
    
    if error_502 > 0:
        print("\n✅ CONFIRMED: File descriptor exhaustion caused 502 errors through Nginx")
    else:
        print("\n❌ NOT CONFIRMED: No 502 errors observed")
    
    # Try to clean up
    try:
        print("\nCleaning up...")
        r = requests.post("http://localhost:8000/cleanup")
        if r.status_code == 200:
            data = r.json()
            print(f"Cleanup complete. Current FD count: {data.get('current_fd_count')}")
        else:
            print(f"Cleanup failed: {r.status_code}")
    except Exception as e:
        print(f"Cleanup error: {e}")

if __name__ == "__main__":
    main() 