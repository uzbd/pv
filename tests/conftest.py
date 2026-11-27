import os

# Configure the ASGI session middleware before app.main is imported by tests.
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-with-more-than-32-characters")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("SESSION_MAX_AGE", "3600")
