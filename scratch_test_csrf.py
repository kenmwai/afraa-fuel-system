import os
import django
from django.test import Client
import re

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

client = Client(enforce_csrf_checks=True)

# 1. Fetch the login page
response = client.get('/accounts/login/')
print(f"GET /accounts/login/ STATUS: {response.status_code}")

if response.status_code == 200:
    content = response.content.decode('utf-8')
    match = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', content)
    if match:
        token = match.group(1)
        print(f"CSRF Token found in HTML: {token[:10]}...")
        
        post_data = {
            'username': 'testuser',
            'password': 'password123',
            'csrfmiddlewaretoken': token
        }
        
        print("Cookies returned by GET:", client.cookies.keys())
        
        response = client.post('/accounts/login/', post_data)
        print(f"POST /accounts/login/ STATUS: {response.status_code}")
        if response.status_code == 403:
            print("CSRF FAILED!")
        else:
            print("CSRF Succeeded, status:", response.status_code)
    else:
        print("No CSRF token found in HTML!")
