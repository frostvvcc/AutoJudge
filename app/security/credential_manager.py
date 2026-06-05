from __future__ import annotations

import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_instance: CredentialManager | None = None


class CredentialManager:
    """
    Local envelope encryption — downgrades AWS KMS to Fernet symmetric encryption.
    Master key is the only secret in the environment; all other credentials
    are encrypted in the database.
    """

    def __init__(self, master_key: str | None = None):
        key = master_key or os.environ.get("MASTER_ENCRYPTION_KEY", "")
        if not key:
            key = Fernet.generate_key().decode()
            logger.warning(
                "MASTER_ENCRYPTION_KEY not set — generated ephemeral key. "
                "Set this env var for persistent credential storage: %s", key,
            )
        if isinstance(key, str):
            key = key.encode()
        self.cipher = Fernet(key)

    def encrypt(self, plaintext: str) -> bytes:
        return self.cipher.encrypt(plaintext.encode("utf-8"))

    def decrypt(self, ciphertext: bytes) -> str:
        if isinstance(ciphertext, str):
            ciphertext = ciphertext.encode("utf-8")
        try:
            return self.cipher.decrypt(ciphertext).decode("utf-8")
        except InvalidToken:
            raise ValueError("Decryption failed — wrong MASTER_ENCRYPTION_KEY or corrupted data")


def get_credential_manager() -> CredentialManager:
    global _instance
    if _instance is None:
        _instance = CredentialManager()
    return _instance
