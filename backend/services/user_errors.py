def to_public_answer_error(exc: Exception) -> str:
    message = str(exc).lower()
    if "embedding error" in message or "rerank error" in message:
        return "AI answer failed. Check your AI provider configuration and try again."
    return "AI answer failed. Please retry."
