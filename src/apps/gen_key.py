import secrets

SECRET_KEY = secrets.token_urlsafe(32)  # Generates a 32-byte (256-bit) secure random key
print(SECRET_KEY)