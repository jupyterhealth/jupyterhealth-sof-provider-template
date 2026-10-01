"""Bridge between SMART launch context and JupyterHealth Exchange data."""

from dotenv import load_dotenv

# Load .env on import so the data layer reads your .env config (JHE_URL,
# MRN_IDENTIFIER_SYSTEM, …) in every run mode, not just under docker compose.
# Does not override variables already set in the environment. No-op if there's no .env.
load_dotenv()
