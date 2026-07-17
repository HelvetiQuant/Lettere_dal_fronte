"""Fake HTML sources for scraper testing."""

ALBO_ORO_HTML = """<!DOCTYPE html>
<html lang="it">
<head>
    <title>Albo d'Oro dei Caduti della Grande Guerra</title>
    <meta name="description" content="Database dei caduti italiani nella Prima Guerra Mondiale">
    <meta name="author" content="Ministero della Difesa">
    <meta name="license" content="dominio pubblico">
    <meta property="og:title" content="Albo d'Oro - Caduti Grande Guerra">
    <meta property="og:description" content="Censimento caduti 1915-1918">
</head>
<body>
    <h1>Albo d'Oro dei Caduti</h1>
    <p>Database completo dei caduti italiani.</p>
    <a href="/scheda/123">Scheda Rossi Mario</a>
    <a href="/documenti/relazione.pdf">Relazione completa (PDF)</a>
    <a href="/images/foto1917.jpg">Fotografia del fronte</a>
    <a href="/images/mappa.png">Mappa operazioni</a>
    <img src="/images/logo.png" alt="Logo">
    <div class="footer">© Stato Maggiore Esercito - Ufficio Storico</div>
</body>
</html>"""

CWGC_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <title>CWGC - Commonwealth War Graves Commission</title>
    <meta name="description" content="War graves and casualties database">
    <meta property="article:published_time" content="2024-01-15">
    <meta name="dc.rights" content="Open Government Licence v3.0">
</head>
<body>
    <h1>Find War Casualties</h1>
    <a href="/casualty/456">Casualty Detail</a>
    <a href="/reports/ww1.pdf">WW1 Report PDF</a>
    <img src="/photos/memorial.jpg" alt="Memorial">
    <div class="footer">© CWGC 2024. All rights reserved.</div>
</body>
</html>"""

NO_META_HTML = """<!DOCTYPE html>
<html>
<head></head>
<body>
    <h1>Page Without Metadata</h1>
    <p>No meta tags here.</p>
    <a href="/doc.pdf">A PDF</a>
</body>
</html>"""

NO_TITLE_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta name="description" content="Page sans titre">
</head>
<body>
    <p>No title tag at all.</p>
</body>
</html>"""

LARGE_HTML = "<html><body>" + "<p>" + "x" * 100 + "</p>" * 10000 + "</body></html>"

ROBOTS_DISALLOW_HTML = """<!DOCTYPE html>
<html><head><title>Blocked</title></head><body>Blocked content</body></html>"""

CC_LICENSE_HTML = """<!DOCTYPE html>
<html lang="it">
<head>
    <title>CC Licensed Content</title>
    <meta name="license" content="CC-BY 4.0">
</head>
<body>
    <h1>Open Content</h1>
    <div class="footer">© 2024 Creative Commons BY 4.0</div>
</body>
</html>"""

FOOTER_COPYRIGHT_HTML = """<!DOCTYPE html>
<html lang="it">
<head><title>Documento Storico</title></head>
<body>
    <h1>Content</h1>
    <div class="footer">© Ufficio Storico SME - Tutti i diritti riservati</div>
</body>
</html>"""

RELATIVE_URLS_HTML = """<!DOCTYPE html>
<html><head><title>Relative URLs</title></head>
<body>
    <a href="docs/report.pdf">Relative PDF</a>
    <a href="../images/photo.jpg">Parent Image</a>
    <img src="assets/logo.png">
</body></html>"""

INVALID_LINKS_HTML = """<!DOCTYPE html>
<html><head><title>Invalid Links</title></head>
<body>
    <a href="javascript:void(0)">JS Link</a>
    <a href="mailto:test@test.com">Mail Link</a>
    <a href="#">Anchor</a>
    <a href="/valid.pdf">Valid PDF</a>
</body></html>"""
