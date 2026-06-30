import os

# run.py builds its DB conninfo from these at import time. The pure functions
# under test never open a connection, so dummy values are enough to import the
# module. setdefault keeps any real env or .env values if present.
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "dbsync")
os.environ.setdefault("DB_USER", "readonly")
