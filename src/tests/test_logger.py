import logging

from app.logger import setup_logger


def test_setup_logger_attaches_file_and_console_handlers_once(tmp_path):
    name = "test.setup_logger.handlers"
    logger = logging.getLogger(name)

    try:
        configured = setup_logger(name, str(tmp_path / "app.log"))
        configured_again = setup_logger(name, str(tmp_path / "app.log"))

        assert configured is logger
        assert configured_again is logger

        file_handlers = [
            handler
            for handler in logger.handlers
            if isinstance(handler, logging.FileHandler)
        ]
        console_handlers = [
            handler
            for handler in logger.handlers
            if isinstance(handler, logging.StreamHandler)
            and not isinstance(handler, logging.FileHandler)
        ]

        assert len(file_handlers) == 1
        assert len(console_handlers) == 1
        assert len(logger.handlers) == 2
    finally:
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()
