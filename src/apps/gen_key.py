import hashlib
import secrets

def generate_api_key():
    """
    Generates a secure random API key and its hashed version.

    This function creates a 64-character (32-byte) hexadecimal API key using 
    `secrets.token_hex(32)`. It then hashes the API key using SHA-256 to 
    produce a secure, irreversible hash.

    Returns:
        None

    Output:
        - Prints the generated API key (must be securely stored by the user).
        - Prints the hashed API key (should be stored in a secure location for authentication purposes).

    Notes:
        - The plaintext API key is only displayed once; if lost, it cannot be recovered.
        - The hashed version should be used for secure storage and verification.
    """
    api_key = secrets.token_hex(32)  # Generates a random 64-character API key
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    
    print("Your API Key (Save this!):", api_key)
    print("Hashed API Key (Store in .env):", api_key_hash)


generate_api_key()
