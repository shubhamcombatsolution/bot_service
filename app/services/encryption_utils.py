from cryptography.fernet import Fernet
import os


SECRET = os.getenv("LLM_ENCRYPTION_KEY", "vX3Kx5q7vT3TQqgq2YQ0nO1E7iH2F7k6Hn5s3aQbYq8=")

if not SECRET:
    raise ValueError("LLM_ENCRYPTION_KEY is not set")

cipher = Fernet(SECRET)


def encrypt_value(key: str) -> str:
    return cipher.encrypt(key.encode()).decode()


def decrypt_value(key: str) -> str:
    return cipher.decrypt(key.encode()).decode()


def mask_key(key: str) -> str:
    if not key or len(key) < 10:
        return "****"
    return key[:6] + "****" + key[-4:]

