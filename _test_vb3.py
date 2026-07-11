"""Analisi dettagliata risposta Volksbund"""
import requests
import re
from html import unescape

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

# GET page
resp = session.get("https://www.volksbund.de/en/erinnern-gedenken/gravesearch-online", timeout=30)

# Extract form tokens
hidden = {}
for m in re.finditer(r'<input[^>]*name="([^"]*)"[^>]*value="([^"]*)"[^>]*type="hidden"', resp.text):
    hidden[m.group(1)] = unescape(m.group(2))
for m in re.finditer(r'<input[^>]*type="hidden"[^>]*name="([^"]*)"[^>]*value="([^"]*)"', resp.text):
    hidden[m.group(1)] = unescape(m.group(2))

form_action = None
m = re.search(r'<form[^>]*action="([^"]*)"', resp.text)
if m:
    form_action = unescape(m.group(1))

# POST search
data = dict(hidden)
data["tx_iggravesearch_list[vdk_Casualty_Last_Name__c]"] = "Muller"
data["tx_iggravesearch_list[vdk_Casualty_First_Name__c]"] = ""
data["tx_iggravesearch_list[vdk_Birthdate_Formatted__c]"] = ""
data["tx_iggravesearch_list[vdk_Place_of_Birth_Website__c]"] = ""
data["tx_iggravesearch_list[date_of_death_or_missing]"] = ""

url = f"https://www.volksbund.de{form_action}" if form_action.startswith('/') else form_action
resp2 = session.post(url, data=data, timeout=60)

# Check what kind of page we got back
# Look for questionnaire / data protection question
questionnaire_keywords = ['questionnaire', 'question', 'fragebogen', 'datenschutz', 'privacy', 'purpose', 'zweck', 'agree', 'accept', 'consent']
found_kw = []
text_lower = resp2.text.lower()
for kw in questionnaire_keywords:
    if kw in text_lower:
        found_kw.append(kw)
print(f"Questionnaire keywords found: {found_kw}")

# Look for a second form (questionnaire)
forms2 = re.findall(r'<form[^>]*>(.*?)</form>', resp2.text, re.DOTALL)
print(f"\nForms in response: {len(forms2)}")
for i, form in enumerate(forms2):
    inputs = re.findall(r'name="([^"]*)"', form)
    if inputs:
        print(f"\n  Form {i} inputs: {inputs}")
    # Check for radio buttons or checkboxes
    radios = re.findall(r'<input[^>]*type="(?:radio|checkbox)"[^>]*name="([^"]*)"[^>]*value="([^"]*)"', form)
    if radios:
        print(f"  Radios/checkboxes: {radios}")
    labels = re.findall(r'<label[^>]*>(.*?)</label>', form, re.DOTALL)
    for l in labels:
        clean = re.sub(r'<[^>]+>', '', l).strip()
        if clean and len(clean) > 5:
            print(f"  Label: {clean[:200]}")

# Also look for the results table
tables = re.findall(r'<table[^>]*class="([^"]*)"', resp2.text)
print(f"\nTables: {tables}")

# Specific search for gravesearch results
ig_sections = re.findall(r'class="[^"]*ig[_-]gravesearch[^"]*"', resp2.text)
print(f"\nIG Gravesearch sections: {ig_sections}")
