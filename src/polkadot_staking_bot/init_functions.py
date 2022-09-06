import logging

from validators import get_validators_info, add_token_rewarded
from nominators import get_nominators, get_nominator_details, get_nominating_summary
from conn import init_substrate, get_active_era


def update_files(init):
    logger = logging.getLogger("polkadot_staking_bot")
    logger.info(f'> Updating files. Init: {init}')
    try:
        substrate = init_substrate()
        era_index = get_active_era(substrate)
        all_nominators = get_nominators(substrate)
        if init:
            for era in range(era_index-28, era_index+1):
                validators_info = get_validators_info(substrate, all_nominators,
                                                      era_index=era, last_era=era_index)
                validators_info = add_token_rewarded(substrate, validators_info, era)
        else:
            validators_info = get_validators_info(substrate, all_nominators,
                                                  era_index=era_index, last_era=era_index)
            validators_info = add_token_rewarded(substrate, validators_info, era_index)

        logger.info(f'> Files updated')
        return validators_info
    except Exception as ex:
        logger.error(f'> 26: {ex}')
        return None


def core(nom):
    substrate = init_substrate()
    era_index = get_active_era(substrate)
    all_nominators = get_nominators(substrate)
    validators_info = get_validators_info(substrate, all_nominators,
                                          era_index=era_index, last_era=era_index)
    validators_info = add_token_rewarded(substrate, validators_info, era_index)
    nominator_details = get_nominator_details(substrate, nom, all_nominators, validators_info, era_index)
    msg = get_nominating_summary(substrate, nominator_details, era_index, nom)
    return msg


def start_logging():
    # Logging
    logging.basicConfig(filename="./polkadot_staking_bot.log",
                        filemode="w",
                        format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%m/%d %H:%M:%S")
    logger = logging.getLogger("polkadot_staking_bot")
    logger.setLevel(logging.INFO)
