"""
PHI Encryption Key Management
==============================
Handles local-development generation and startup validation of the
Fernet key used for PHI-at-rest encryption (``PHI_ENCRYPTION_KEY``,
consumed by ``app.core.security.encrypt_phi`` / ``decrypt_phi``, and by
extension `app.agents.phi_tokenization.storage`'s optional
`set_encryption` hook).

This module deliberately does NOT import ``app.core.config`` -- it has
to run *before* ``Settings`` is constructed, so that the key already
exists in the environment / local ``.env`` file by the time
``Settings`` reads it. ``app.core.config`` imports and calls
``ensure_phi_encryption_key`` for exactly this reason.

Guarantees
----------
- An existing key -- whether set as a real process environment
  variable or already present in the local ``.env`` file -- is NEVER
  regenerated or overwritten.
- A new key is generated ONLY when no key is found anywhere, and ONLY
  outside production. In production (``APP_ENV=production``) a key
  must be provisioned through a proper secrets manager; this module
  will not silently mint a throwaway one.
- The key value itself is never logged, printed, or otherwise
  returned to any log/response -- only the fact that a key was (or was
  not) found/generated.
- The generated key is written to the local ``.env`` file ONLY. It is
  never written anywhere else in the repository, and it is never
  committed (``.env`` is already git-ignored).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import dotenv_values, set_key

log = logging.getLogger(__name__)

ENV_VAR_NAME = "PHI_ENCRYPTION_KEY"

# Matches the relative path pydantic-settings' `Settings` (env_file=".env")
# resolves against the process's current working directory, so the key we
# write ends up in the exact same file `Settings` will read.
DEFAULT_ENV_PATH = Path(".env")


def is_valid_fernet_key(key: str) -> bool:
    """Return True if *key* is a structurally valid Fernet key.

    Never logs or raises with the key value.
    """
    if not key:
        return False
    try:
        Fernet(key.encode() if isinstance(key, str) else key)
        return True
    except Exception:
        return False


def _existing_key(env_path: Path) -> str | None:
    """Return the current key value if one exists anywhere.

    Checks the real process environment first (that's also what takes
    precedence in pydantic-settings), then falls back to the local
    ``.env`` file. Returns None if no key is configured yet.
    """
    value = os.environ.get(ENV_VAR_NAME)
    if value:
        return value

    if env_path.exists():
        value = dotenv_values(env_path).get(ENV_VAR_NAME)
        if value:
            return value

    return None


def ensure_phi_encryption_key(env_path: Path | str = DEFAULT_ENV_PATH) -> None:
    """Guarantee a PHI_ENCRYPTION_KEY is available for local development.

    - If a key already exists (env var or ``.env`` file), this is a
      no-op -- the existing key is left completely untouched.
    - If no key exists and the app is not running as production, a new
      Fernet key is generated and persisted to the local ``.env`` file
      (created if necessary) *and* to the current process environment,
      so ``Settings`` picks it up immediately on this run.
    - In production, no key is generated. The setting is left empty so
      the explicit startup validation (see ``validate_phi_encryption_key``
      in ``app.core.config``) fails loudly and specifically, rather
      than a key silently appearing for a production deployment.

    The generated key value is never logged, printed, or returned.
    """
    env_path = Path(env_path)

    if _existing_key(env_path) is not None:
        return  # never regenerate an existing key

    app_env = os.environ.get("APP_ENV", "development").strip().lower()
    if app_env == "production":
        log.warning(
            "phi_encryption_key_missing_in_production: refusing to "
            "auto-generate a key; provision PHI_ENCRYPTION_KEY via your "
            "secrets manager."
        )
        return

    new_key = Fernet.generate_key().decode()

    if not env_path.exists():
        env_path.touch()

    # `set_key` writes/updates only the PHI_ENCRYPTION_KEY line in the
    # .env file, leaving every other line untouched.
    set_key(str(env_path), ENV_VAR_NAME, new_key, quote_mode="never")

    # Make it available to this process immediately in case Settings()
    # is constructed before re-reading the file.
    os.environ[ENV_VAR_NAME] = new_key

    log.info(
        "phi_encryption_key_generated: a new local development "
        "PHI_ENCRYPTION_KEY was generated and stored in %s",
        str(env_path),
    )