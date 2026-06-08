from __future__ import annotations

import logging
import os

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


class CredentialManager:
    """
    Local envelope encryption using Fernet (AES-128-CBC + HMAC-SHA256).

    Master Key is the only plaintext secret — loaded from MASTER_ENCRYPTION_KEY
    env var. All other credentials are encrypted before storage.
    """

    def __init__(self):
        master_key = os.environ.get("MASTER_ENCRYPTION_KEY")
        if not master_key:
            master_key = Fernet.generate_key().decode()
            logger.warning(
                "MASTER_ENCRYPTION_KEY not set — generated ephemeral key: %s  "
                "Save this to a secure location and set as env var for production.",
                master_key,
            )
        key = master_key.encode() if isinstance(master_key, str) else master_key
        self.cipher = Fernet(key)

    def encrypt(self, plaintext: str) -> bytes:
        return self.cipher.encrypt(plaintext.encode())

    def decrypt(self, ciphertext: bytes) -> str:
        return self.cipher.decrypt(ciphertext).decode()


credential_manager = CredentialManager()
