This directory is the ONLY location the agent is permitted to write files.

Rules (hardcoded in services/action/safety/path_validator.py):
  - All write targets must resolve inside this directory.
  - Only .json files are permitted.
  - A timestamped backup is created before any overwrite.
  - Path traversal attempts raise PathTraversalError and are audit-logged.
