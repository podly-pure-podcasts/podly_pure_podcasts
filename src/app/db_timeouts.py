"""SQLite timing shared by the app factory and the writer client.

Kept out of app/__init__.py so the writer client can import it without an import cycle.
"""

# How long a statement waits for the database lock before SQLite gives up. Longer
# than the default to allow large batch deletes/updates to finish.
SQLITE_BUSY_TIMEOUT_MS = 90000
