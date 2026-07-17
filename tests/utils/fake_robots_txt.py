"""Fake robots.txt responses for testing."""

ROBOTS_ALLOW_ALL = """User-agent: *
# No restrictions
"""

ROBOTS_DISALLOW_ALL = """User-agent: *
Disallow: /
"""

ROBOTS_DISALLOW_PDF = """User-agent: *
Disallow: /documenti/
Disallow: *.pdf
"""

ROBOTS_DISALLOW_SPECIFIC = """User-agent: *
Disallow: /private/
Allow: /public/

User-agent: BadBot
Disallow: /
"""

ROBOTS_EMPTY = ""

ROBOTS_MALFORMED = """This is not a valid robots.txt
%%%garbage%%%
User-agent: *
Disallow: /blocked
"""
