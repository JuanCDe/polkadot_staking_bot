# Polkadot Staking Bot
# By JuanCDe
# Following structure by https://guicommits.com/organize-python-code-like-a-pro/
import logging
import datetime
import time

from conn import retrieve_ss58_registry
from init_functions import update_files, start_logging
from telegramBot import start_bot, stop_bot


if __name__ == "__main__":
    # Init logging
    start_logging()
    logger = logging.getLogger("polkadot_staking_bot")
    logger.info(f'> Starting')

    # Obtain networks info
    retrieve_ss58_registry()

    # Populate last n eras
    update_files(init=True)

    # Start listening
    try:
        start_bot()
    except Exception as ex:
        logger.error(f'> 26 (init) {ex}')
        stop_bot()
        exit(1)

    # Keep it running and update it once everyday
    try:
        while True:
            time.sleep(1)
            if datetime.datetime.now().strftime("%H:%M") == "15:00":
                logger.info(f'> Updating')
                update_files(init=False)
                logger.info(f'> Updated')
                time.sleep(60)
    except KeyboardInterrupt:
        logger.error(f'> Stopping by interruption')
        stop_bot()
