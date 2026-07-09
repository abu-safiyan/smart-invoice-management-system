import logging
from pathlib import Path

LOGS_DIR = Path(__file__).parent.parent/'logs'
LOGS_DIR.mkdir(parents=True, exist_ok=True)

def get_logger():
    logger = logging.getLogger('system_logger')
    logger.propagate = False
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler(LOGS_DIR/'system_logs.log')
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger