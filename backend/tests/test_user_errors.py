from services.user_errors import to_public_answer_error


def test_provider_error_is_sanitized_for_user_display():
    message = to_public_answer_error(
        RuntimeError(
            "Embedding error: Access denied, please make sure your account is in good standing. "
            "For details, see: https://www.alibabacloud.com/help/en/model-studio/error-code#overdue-payment"
        )
    )

    assert message == "AI answer failed. Check your AI provider configuration and try again."


def test_unexpected_error_is_also_sanitized_for_user_display():
    message = to_public_answer_error(RuntimeError("boom"))

    assert message == "AI answer failed. Please retry."
