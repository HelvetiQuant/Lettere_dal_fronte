"""Test Volksbund Gräbersuche form submission"""
import requests
import re
from html import unescape

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
})

# Step 1: Get the search page and extract CSRF tokens
url = "https://www.volksbund.de/en/erinnern-gedenken/gravesearch-online"
resp = session.get(url, timeout=30)
print(f"GET Status: {resp.status_code}")

# Extract form action
form_match = re.search(r'<form[^>]*action="([^"]*)"[^>]*>', resp.text)
form_action = unescape(form_match.group(1)) if form_match else None
print(f"Form action: {form_action}")

# Extract hidden fields
hidden_fields = {}
for m in re.finditer(r'<input[^>]*type="hidden"[^>]*name="([^"]*)"[^>]*value="([^"]*)"', resp.text):
    hidden_fields[m.group(1)] = unescape(m.group(2))
# Also try reversed order (value before name)
for m in re.finditer(r'<input[^>]*value="([^"]*)"[^>]*type="hidden"[^>]*name="([^"]*)"', resp.text):
    hidden_fields[m.group(2)] = unescape(m.group(1))

print(f"\nHidden fields: {list(hidden_fields.keys())}")
for k, v in hidden_fields.items():
    print(f"  {k}: {v[:100]}")

# Step 2: Submit search with last name = "Muller" (common German name)
form_data = dict(hidden_fields)
form_data["tx_iggravesearch_list[vdk_Casualty_Last_Name__c]"] = "Muller"
form_data["tx_iggravesearch_list[vdk_Casualty_First_Name__c]"] = ""
form_data["tx_iggravesearch_list[vdk_Birthdate_Formatted__c]"] = ""
form_data["tx_iggravesearch_list[vdk_Place_of_Birth_Website__c]"] = ""
form_data["tx_iggravesearch_list[date_of_death_or_missing]"] = ""

post_url = f"https://www.volksbund.de{form_action}" if form_action and form_action.startswith('/') else form_action
print(f"\nPOST to: {post_url}")

resp2 = session.post(post_url, data=form_data, timeout=60)
print(f"POST Status: {resp2.status_code}")
print(f"Response Length: {len(resp2.text)}")

# Check for CAPTCHA or questionnaire
if 'captcha' in resp2.text.lower() or 'recaptcha' in resp2.text.lower():
    print("\n*** CAPTCHA DETECTED ***")
    captcha_type = re.findall(r'(?:g-recaptcha|hcaptcha|turnstile|captcha)[^"]*', resp2.text.lower())
    print(f"  Type: {captcha_type}")

# Look for results
results_section = re.findall(r'class="[^"]*result[^"]*"', resp2.text, re.IGNORECASE)
print(f"\nResult classes: {results_section[:10]}")

# Find result count
count_match = re.search(r'(\d+)\s*(?:results?|Ergebnisse?|Treffer|records?|entries?)', resp2.text, re.IGNORECASE)
if count_match:
    print(f"\nResult count: {count_match.group(0)}")

# Print section around 'result' or 'Muller'
idx = resp2.text.lower().find('muller')
if idx > 0:
    print(f"\n=== 'muller' context ===")
    # Clean HTML
    section = resp2.text[max(0,idx-200):idx+500]
    clean = re.sub(r'<[^>]+>', ' ', section)
    clean = re.sub(r'\s+', ' ', clean).strip()
    print(clean[:500])
else:
    # Check for redirect or error
    print("\n'muller' not found in response")
    # Print relevant section
    idx = resp2.text.lower().find('grave')
    if idx > 0:
        section = resp2.text[max(0,idx-100):idx+500]
        clean = re.sub(r'<[^>]+>', ' ', section)
        clean = re.sub(r'\s+', ' ', clean).strip()
        print(f"\n=== 'grave' context ===")
        print(clean[:500])
