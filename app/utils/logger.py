from __future__ import annotations

import logging
import os
import sys

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

def setup_logger() -> logging.Logger:
    env_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, env_level, logging.INFO)

    logging.basicConfig(
        level=log_level,
        format=LOG_FORMAT,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True
    )
    
    noisy_libs = ["httpcore", "httpx", "websockets", "asyncio", "sqlalchemy", "urllib3", "google"]
    for lib in noisy_libs:
        logging.getLogger(lib).setLevel(logging.WARNING)

    return logging.getLogger("asistente_agro")

logger = setup_logger()
