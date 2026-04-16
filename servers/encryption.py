"""
Encryption utilities for server credential storage.
Moved from passwords/encryption.py — passwords/ module is being retired.
"""
import os
import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from loguru import logger


class PasswordEncryption:
    """Handle encryption/decryption of server credentials."""

    @staticmethod
    def _get_key_from_password(password: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend(),
        )
        return base64.urlsafe_b64encode(kdf.derive(password.encode()))

    @staticmethod
    def encrypt_password(password: str, master_password: str, salt: bytes) -> str:
        try:
            key = PasswordEncryption._get_key_from_password(master_password, salt)
            fernet = Fernet(key)
            encrypted = fernet.encrypt(password.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise

    @staticmethod
    def decrypt_password(encrypted_password: str, master_password: str, salt: bytes) -> str:
        try:
            if not master_password:
                raise ValueError("MASTER_PASSWORD пустой — расшифровка невозможна")
            if not salt:
                raise ValueError("Salt пустой — расшифровка невозможна")
            key = PasswordEncryption._get_key_from_password(master_password, salt)
            fernet = Fernet(key)
            try:
                encrypted_bytes = base64.urlsafe_b64decode((encrypted_password or "").encode())
            except Exception as e:
                raise ValueError("Секрет повреждён: некорректный base64") from e
            try:
                decrypted = fernet.decrypt(encrypted_bytes)
            except InvalidToken as e:
                raise ValueError("Неверный мастер‑пароль или повреждённый секрет") from e
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Decryption failed ({type(e).__name__}): {e!r}")
            raise

    @staticmethod
    def generate_salt() -> bytes:
        return os.urandom(16)

    @staticmethod
    def generate_password(length: int = 16, include_symbols: bool = True) -> str:
        import secrets
        import string

        alphabet = string.ascii_letters + string.digits
        if include_symbols:
            alphabet += "!@#$%^&*()_+-=[]{}|;:,.<>?"
        return "".join(secrets.choice(alphabet) for _ in range(length))
