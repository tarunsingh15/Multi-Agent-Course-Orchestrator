"""
This module provides a simple utility function to generate unique UIDs.
"""
import random
import string

id_length = 6

def generate_uid() -> str:
    """
    Generates a unique user ID with a 'USR-' prefix.
    """
    suffix = "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(id_length))
    return f"USR-{suffix}"