import requests
import json
import sys

# Try to hit the backend directly (port 8000)
# to see if the 500 is coming from FastAPI or Next.js Proxy
url = "http://localhost:8000/api/auth/login"
payload = {
    "email": "admin@example.com",
    "password": "changeme123"
}
headers = {
    "Content-Type": "application/json"
}

print(f"Testing direct connection to {url}...")
try:
    response = requests.post(url, json=payload, headers=headers, timeout=10)
    print(f"Status Code: {response.status_code}")
    print(f"Response Body: {response.text}")
except Exception as e:
    print(f"Error connecting to backend directly: {e}")
