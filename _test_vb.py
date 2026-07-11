"""Test Volksbund Gräbersuche API"""
import requests
import re
import json

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})

# Get the search page
url = "https://www.volksbund.de/en/erinnern-gedenken/gravesearch-online/"
resp = session.get(url, timeout=30)
print(f"Status: {resp.status_code}, Length: {len(resp.text)}")

# Find form action
forms = re.findall(r'<form[^>]*action="([^"]*)"[^>]*>', resp.text)
print(f"Forms: {forms}")

# Find AJAX/API endpoints
api_hints = re.findall(r'(?:url|endpoint|action|api)["\s:=]+["\']([^"\']+)["\']', resp.text, re.IGNORECASE)
print(f"\nAPI hints: {[h for h in api_hints if 'volksbund' in h or '/' in h][:20]}")

# Find scripts
scripts = re.findall(r'src="([^"]*\.js[^"]*)"', resp.text)
print(f"\nScripts: {scripts[:10]}")

# Find any JSON config
json_blocks = re.findall(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', resp.text, re.DOTALL)
print(f"\nJSON configs: {len(json_blocks)}")
for jc in json_blocks[:3]:
    print(jc[:500])

# Look for CSRF tokens or form fields
inputs = re.findall(r'<input[^>]*name="([^"]*)"[^>]*>', resp.text)
print(f"\nForm inputs: {inputs}")

# Try to find the search endpoint directly
search_patterns = re.findall(r'["\']([^"\']*(?:search|suche|graber|graeber)[^"\']*)["\']', resp.text, re.IGNORECASE)
print(f"\nSearch patterns: {search_patterns[:20]}")
