import logging

from rag_api.request_context import request_id_var, user_id_var


def test_logging_config():
    """The configured JSON formatter must embed the current request_id and
    user_id context values in every formatted log line.
    """
    from rag_api.logging_config import JsonLogFormatter, configure_logging

    request_id_token = request_id_var.set("test-request-id")
    user_id_token = user_id_var.set("test-user-id")
    try:
        configure_logging()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="test-message",
            args=(),
            exc_info=None,
        )
        formatted = JsonLogFormatter().format(record)

        assert "test-request-id" in formatted
        assert "test-user-id" in formatted
    finally:
        request_id_var.reset(request_id_token)
        user_id_var.reset(user_id_token)
