"""Shared constants for web resolution and navigation."""

# Common domain mapping for URL resolution and fallback
# Maps common keywords to their canonical URLs
COMMON_DOMAINS = {
    "youtube": "www.youtube.com",
    "gmail": "mail.google.com",
    "google": "www.google.com",
    "github": "github.com",
    "twitter": "twitter.com",
    "facebook": "www.facebook.com",
    "linkedin": "www.linkedin.com",
    "reddit": "www.reddit.com",
    "instagram": "www.instagram.com",
    "amazon": "www.amazon.com",
}

# Scoring weights for link candidate ranking
SCORE_EXACT_TEXT_MATCH = 10.0  # Exact query match in link text
SCORE_ARIA_LABEL_MATCH = 5.0   # Query match in aria-label attribute
SCORE_PER_TERM_MATCH = 2.0     # Each matching query term
