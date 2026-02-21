from uuid import uuid4


def generate_application_id(prefix: str) -> str:
    normalized = prefix.strip().lower().replace(" ", "-")
    return f"{normalized}_{uuid4()}"
