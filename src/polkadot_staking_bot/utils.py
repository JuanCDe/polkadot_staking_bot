from os.path import exists, getmtime
from datetime import datetime
import pickle
from scalecodec.utils.ss58 import is_valid_ss58_address
import logging
import math


# def create_logger():
#     logging.basicConfig(filename="./staking_info.log",
#                         filemode="w",
#                         format="%(asctime)s %(levelname)s %(message)s",
#                         datefmt="%m/%d %H:%M:%S")
#
#     logger = logging.getLogger("stakinginfo")
#     logger.setLevel(logging.INFO)
#     return logger


def get_pos_percentile(val_list, value):
    if value not in val_list:
        val_list = list(val_list + [value])
    val_list.sort(reverse=True)
    len_list = len(val_list)
    value_pos = val_list.index(value) + 1
    top_percentile = (value_pos/len_list) * 100
    percentile_rounded = round(top_percentile, 2)
    result = {"len_list": len_list, "value_pos": value_pos, "percentile_rounded": percentile_rounded}
    return result


def add_emoji_status(status):
    if status == "Nominated":
        emoji = "\U00002705"
    elif status == "Active":
        emoji = "\U0001F7E7"
    elif status == "Waiting":
        emoji = "\U0001F551"
    else:
        emoji = "\U0000274C NOT VALIDATING"
    return emoji


def add_emoji_position(percentile):
    if percentile < 5:
        emoji = "\U0001F60A"
    elif percentile < 25:
        emoji = "\U0001F600"
    elif percentile < 50:
        emoji = "\U0001F642"
    elif percentile < 75:
        emoji = "\U0001F928"
    elif percentile < 90:
        emoji = "\U0001F626"
    else:
        emoji = "\U0001F6A8"
    return emoji


def file_status(file):
    logger = logging.getLogger("polkadot_staking_bot")
    data = {}
    if exists(file):
        creation_time = getmtime(file)
        minutes_from_creation = ((datetime.now() - datetime.fromtimestamp(creation_time)).seconds / 60)
        if minutes_from_creation < 60:
            run = False
            logger.info(f'> Loading {file}...')
            with open(file, 'rb') as input_data:
                data = pickle.load(input_data)
        else:
            logger.info(f'> Refreshing {file}...')
            run = True
    else:
        logger.info(f'> Creating {file}...')
        run = True

    return run, data


def validate_addr(addr):
    with open("./src/data/ss58_registry_dict.pkl", 'rb') as input_data:
        registry_dict = pickle.load(input_data)

    for k, v in registry_dict.items():
        right_format = is_valid_ss58_address(addr, valid_ss58_format=k)
        if right_format:
            return v
    return "Invalid address"


def generate_legend():
    msg = f'/legend\n' \
          f'*ERA SECTION*\n\n' \
          f'\U0001F449: Link to the nominator address in Subscan\n\n' \
          f'\U0001F969: Staked tokens for the past or current era\n\n' \
          f'\U0001F4B0: Reward obtained from the past era and its approximate APR\n\n' \
          f'\U0001F969: Bonded tokens for the current era\n\n' \
          f'\n\n*VALIDATOR SECTION*\n\n' \
          f'✅> Validator is the "Active" one (validating with your funds)\n\n' \
          f'🟧> Validator is "Inactive" (validating but not with your funds)\n\n' \
          f'🕑> Validator not validating (out of the top 297, but want to)\n\n' \
          f'❌ NOT VALIDATING> The validator has NO intentions to validate for this era\n\n' \
          f'\U0001F9FE: x.x% represents the fee from the validator. _(x.x% -> y.y%)_ would represent a fee change\n\n' \
          f'\U0001F5F3: Number of nominators nominating it / Number of nominators with it as the Active validator\n\n' \
          f'\U00002696: The validator is oversuscribed (+256 nominators have it as their Active validator)\n\n' \
          f'"\U0001F4CA": The % of the total amount staked on the validator owned by the nominator' \
          f'❗: The nominator is (or would be) out of the top 256 of the nominating list\n\n' \
          f'\U0001F3C5: Position of the nominator in the validator list (the "would-be" position if the validator is not the Active)\n\n' \
          f'_top x.x%_: Percentage from the top (percentile)\n\n' \
          f'\U0001F60A \U0001F600 \U0001F642 \U0001F928 \U0001F626 \U0001F6A8: The happier, the better position\n\n' \
          f'\U0001F4A9: One of the nominated validators was slashed\n\n' \
          f'\U0001F52A\U0001FA78: Nominator was slashed\n' \
          f'/start'
    return msg


def generate_bot_disclaimer():
    msg = f"/disclaimer \n" \
          f"*DISCLAIMER*\n\n" \
          f"- This bot is for superficial information only. It's built with no intentions of being " \
          f"the definitive source of truth.\n\n" \
          f"- Actions done by the user after using the bot is solely under user's responsibility." \
          f" Check other sources before doing anything stupid!\n\n" \
          f"- The bot *respects privacy*. It does not storage any address or user's ID. That's why the " \
          f"nominator's address must be entered everytime. You, the user, *do not subscribe* to any address so" \
          f" the bot won't remember you. If you want to be remembered, do something important.\n\n" \
          f"- I built this bot for personal use, but it went out of hands. I think it's helpful." \
          f" If you don't think so, delete the chat and it won't bother you ever again. Pinky promise.\n\n" \
          f"- There's a long ToDo list, but if you want something added, removed, changed, or found any error," \
          f" contact me @Juan\_CDe\n" \
          f"/start"
    return msg


def short_addr(addr):
    sh_add = addr.replace(addr[4:-4], "...")
    return sh_add


def human_readable(x):
    try:
        zeros = int(math.log10(x))
        if zeros >= 3 and zeros < 6:
            return f"{round(x/1e3, 2)}K"
        elif(zeros >= 6 and zeros < 9):
            return f"{round(x/1e6, 2)}M"
        elif(zeros >= 9):
            return f"{round(x/1e9, 2)}B"
        else:
            return f"{round(x, 6)}"
    except ValueError:
        return f'0'