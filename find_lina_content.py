# -*- coding: utf-8 -*-
"""Cerca 'Lina' come parola dentro TUTTI i documenti dell'utente."""
import os, re, sys, zipfile

sys.stdout.reconfigure(errors='replace')
import fitz  # PyMuPDF

WORD = re.compile(r'\b[Ll][Ii][Nn][Aa]\b')
WORD_B = re.compile(rb'\b[Ll][Ii][Nn][Aa]\b')

SKIP_DIR = re.compile(
    r'AppData|node_modules|\.venv|venv\\|\.git\\|__pycache__|'
    r'Package Cache|\.cache\\|\.codex\\|\.devin\\|\.lmstudio\\|'
    r'models\\|huggingface|\.npm|\.nuget|site-packages|'
    r'fondi_pdfs|data_mdh|exports|codex_handoff', re.I)
TXT_EXT = ('.txt', '.md', '.rtf', '.csv', '.html', '.htm', '.log',
           '.xml', '.json', '.scrivx', '.tex', '.py', '.ini', '.yaml', '.yml')
ZIP_EXT = ('.docx', '.xlsx', '.pptx', '.odt', '.ods', '.epub')

ROOTS = [
    r'C:\Users\eryma\Desktop',
    r'C:\Users\eryma\Documents',
    r'C:\Users\eryma\Downloads',
    r'C:\Users\eryma\OneDrive',
    r'C:\Users\eryma\CascadeProjects',
    r'C:\Users\eryma\Pictures',
    r'C:\Users\eryma\Music',
    r'C:\Users\eryma\Videos',
    r'C:\Users\eryma',
]

def text_from_zip(path):
    try:
        out = []
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if n.endswith('.xml') and ('document' in n or 'sheet' in n
                                          or 'content' in n or 'slide' in n
                                          or 'sharedStrings' in n):
                    out.append(z.read(n).decode('utf-8', 'ignore'))
        return ' '.join(out)
    except Exception:
        return ''

def text_from_pdf(path):
    try:
        doc = fitz.open(path)
        return ' '.join(page.get_text() for page in doc)
    except Exception:
        return ''

seen = set()
hits = []
scanned = 0
for root_dir in ROOTS:
    if not os.path.isdir(root_dir):
        continue
    for root, sub, fs in os.walk(root_dir):
        if SKIP_DIR.search(root):
            sub[:] = []
            continue
        for fn in fs:
            p = os.path.join(root, fn)
            if p in seen:
                continue
            seen.add(p)
            low = fn.lower()
            try:
                if low.endswith(ZIP_EXT):
                    scanned += 1
                    t = text_from_zip(p)
                    if WORD.search(t):
                        hits.append((p, len(WORD.findall(t)), 'zip'))
                elif low.endswith('.pdf'):
                    scanned += 1
                    t = text_from_pdf(p)
                    if WORD.search(t):
                        hits.append((p, len(WORD.findall(t)), 'pdf'))
                elif low.endswith(TXT_EXT):
                    scanned += 1
                    data = open(p, 'rb').read(2_000_000)
                    if WORD_B.search(data):
                        hits.append((p, len(WORD_B.findall(data)), 'txt'))
            except Exception:
                pass

for p, n, kind in sorted(hits):
    print(f'{n:>4}x [{kind}] {p}')
print(f'\n== {scanned} file scansionati, {len(hits)} con corrispondenze ==')
