"""
DEPRECATED: passwords/ module is being retired.
All consumers have been migrated to servers.encryption.
This file exists only as a safety net during the transition.
"""
from servers.encryption import PasswordEncryption  # noqa: F401

__all__ = ["PasswordEncryption"]
