import os
import tempfile

# app.main builds a default app at import; keep its cache out of the repo.
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())
