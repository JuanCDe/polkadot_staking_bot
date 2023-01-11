import pickle
import logging

from utils import file_status, get_pos_percentile, add_emoji_position, add_emoji_status, short_addr
from validators import get_identity_info


def get_nominators(substrate):
    """
    Obtiene la lista de nominadores que muestran intención de nominar
    :param substrate: Conexión al RPC
    :return: Diccionario con formato {nom_address: {"validators_nominated": [addr]}}
    """
    logger = logging.getLogger("polkadot_staking_bot")
    run, nominators_all = file_status(file='./src/data/nominators_info.pkl')

    if run:
        nominators_all = {}
        nominators = substrate.query_map(
            module='Staking',
            storage_function='Nominators',
            page_size=1000
        )
        nominator_temp = {val[0].value: {"validators_nominated": val[1]["targets"].value} for val in nominators.records}
        nominators_all = {**nominators_all, **nominator_temp}
        end = False
        while not end:
            if len(nominators.records) < 1000:
                logger.info(f'> Active nominators: {len(nominators_all)}')
                end = True
            else:
                nominators = substrate.query_map(
                    module='Staking',
                    storage_function='Nominators',
                    page_size=1000,
                    start_key=nominators.last_key
                )
                nominator_temp = {val[0].value: {"validators_nominated": val[1]["targets"].value} for val in
                                  nominators.records}
                nominators_all = {**nominators_all, **nominator_temp}
        # Añadir conteo de validadores nominados por cada nominador
        # Se usará para calcular el apoyo a cada validador (sum(stake_nom_i/num_valj_nom_i))
        for nom in nominators_all:
            nominators_all[nom]["num_nominatig"] = len(nominators_all[nom]["validators_nominated"])
        with open('./src/data/nominators_info.pkl', 'wb') as output_data:
            pickle.dump(nominators_all, output_data)

    return nominators_all


def get_staking_nominator(substrate, addr):
    to_units = 10 ** substrate.token_decimals
    bonded_addr = substrate.query(
        module='Staking',
        storage_function='Bonded',
        params=[addr]
    ).value

    stash_addr = bonded_addr if bonded_addr else addr
    staked_by_nominator = substrate.query(
        module='Staking',
        storage_function='Ledger',
        params=[stash_addr]
    ).value

    staked_by_nominator = staked_by_nominator["active"]/to_units if staked_by_nominator else None

    return staked_by_nominator


def get_nominator_details(substrate, nom, all_nominators, validators_info, era_index):
    try:
        currently_bonded = get_staking_nominator(substrate, nom)
        current_active_nom_full = {"active_noms": {}, "currently_staking": 0}
        apr = 0
        nominated = {}
        slashed_info = ""
        perc_on_validator = 0
        if currently_bonded and nom in all_nominators:
            slashed_nominator_msj = nom_was_slashed(substrate, validators_info, nom)

            # Validators the nominator is staking with this era
            current_active_nom_full = get_active_nominated(validators_info, nom, era_index)
            currently_staking = current_active_nom_full["currently_staking"]
            for staking_val, staked in current_active_nom_full["active_noms"].items():
                nominated[staking_val] = validators_info.get(staking_val)
                nominated[staking_val]["era_info"][era_index]["status"] = "Staked"

                staking_nominators = validators_info[staking_val]["era_info"][era_index]["nominators"]
                prct_pos = get_pos_percentile(list(staking_nominators.values()), staked)
                nominated[staking_val]["era_info"][era_index]["nom_pos"] = prct_pos["value_pos"]
                nominated[staking_val]["era_info"][era_index]["nom_percentile"] = prct_pos["percentile_rounded"]
                nominated[staking_val]["era_info"][era_index]["len_nominators"] = prct_pos["len_list"]

                total_stake_by_val = float(validators_info[staking_val]["era_info"][era_index]["total_stake"])
                currently_staking_on_val = current_active_nom_full["active_noms"][staking_val]
                nominated[staking_val]["era_info"][era_index]["perc_on_active_val"] = currently_staking_on_val*100/total_stake_by_val

            # Validators that are currently nominated (they don't have to be the ones staking with)
            for validator in all_nominators[nom]["validators_nominated"]:
                if validators_info.get(validator):
                    nominated[validator] = validators_info.get(validator)

                    status = validators_info[validator]["era_info"][era_index]["status"]
                    if status == "Active":
                        staking_nominators = validators_info[validator]["era_info"][era_index]["nominators"]
                        nominated[validator]["era_info"][era_index]["status"] = status
                        prct_pos = get_pos_percentile(list(staking_nominators.values()), currently_staking)
                        nominated[validator]["era_info"][era_index]["nom_pos"] = prct_pos["value_pos"]
                        nominated[validator]["era_info"][era_index]["nom_percentile"] = prct_pos["percentile_rounded"]
                        nominated[validator]["era_info"][era_index]["len_nominators"] = prct_pos["len_list"]

                        slashed_validator_msj = val_was_slashed(validator, validators_info)
                        slashed_info = slashed_nominator_msj + slashed_validator_msj

                else:
                    status = "NOT A VALIDATOR"
                    nominated.update({validator: {"era_info": {era_index: {"status": status}}}})

            for validators_in_nom in nominated:
                nominated[validators_in_nom]["identity_info"] = get_identity_info(substrate, validators_in_nom)
                if validators_info.get(validators_in_nom):
                    status = validators_info[validators_in_nom]["era_info"][era_index]["status"]
                else:
                    status = nominated[validators_in_nom]["era_info"][era_index]["status"]
                nominated[validators_in_nom]["era_info"][era_index]["status_order"] = add_order(status)

        else:
            nominated = None

        past_era = era_index-1
        past_reward, past_staking = get_past_staking_rewards(validators_info, nom, past_era)
        if past_reward and past_staking:
            apr = round(past_reward*100*365/past_staking, 2)
        result = {"staking_with": current_active_nom_full, "nominated": nominated,
                  "past_reward": past_reward, "staked_past_era": past_staking, "apr": apr,
                  "currently_staking": current_active_nom_full["currently_staking"], "currently_bonded": currently_bonded,
                  "perc_on_validator": perc_on_validator, "slashed": slashed_info}
        return result
    except Exception as ex:
        print("141 ", ex)


def get_nominating_summary(substrate, nominator_details, era_index, nom):
    nominated = nominator_details["nominated"]
    past_reward = round(nominator_details["past_reward"], 4)
    slashed_info = nominator_details["slashed"]
    staked_past_era = round(nominator_details["staked_past_era"], 4)
    apr = nominator_details["apr"]
    if nominated:
        nom_shorted = short_addr(nom)
        nom_link = f'[{nom_shorted}](https://polkadot.subscan.io/account/{nom})'
        currently_staking = round(nominator_details["currently_staking"], 4)
        currently_bonded = round(nominator_details["currently_bonded"], 5)

        token_symbol = substrate.token_symbol
        to_print = f'\U0001F449 {nom_link}\n\n' \
                   f'\U0001F4C5 Past era {era_index-1}\n' \
                   f'{" "*8}\U0001F969 {staked_past_era} {token_symbol}\n' \
                   f'{" "*8}\U0001F4B0 *{past_reward} {token_symbol}* (~{apr}% APR)\n\n' \
                   f'\U0001F4C5 Current era *{era_index}*\n' \
                   f'{" "*8}\U0001F969 {currently_staking} {token_symbol}\n' \
                   f'{" "*8}\U0001F517 {currently_bonded} {token_symbol}\n\n'
        nominated = dict(sorted(nominated.items(), key=lambda item: item[1]["era_info"][era_index]["status_order"]))
        for validator in nominated:
            identity_display = nominated[validator]["identity_info"]["display_name"]
            identity_val = f'[{identity_display}](https://polkadot.subscan.io/account/{validator})'
            info_current_era = nominated[validator]["era_info"][era_index]
            current_status = info_current_era["status"]

            info_previous_era = nominated[validator]["era_info"].get(era_index-1)
            previous_status = info_previous_era["status"] if info_previous_era else info_current_era["status"]

            if current_status != "NOT A VALIDATOR" and previous_status != "NOT A VALIDATOR":
                current_commission = info_current_era["commission"]
                previous_commission = info_previous_era["commission"] if info_previous_era else info_current_era["commission"]
                commission_change = previous_commission != current_commission
                commission = f'{previous_commission}% -> {current_commission}' if commission_change else current_commission
                total_nominators = nominated[validator]["era_info"][era_index]["total_nominators"]
                if current_status == "Active" or current_status == "Staked":
                    active_nominators = info_current_era["active_nominators"]
                    if current_status == "Staked":
                        # Se suma 1 si el validador no es el nominado ya que sería el supuesto de que formase parte de su lista
                        active_nominators = active_nominators+1
                        perc_on_active_val = round(info_current_era["perc_on_active_val"], 2)
                        perc_on_active_val_msg = f'{" "*8}\U0001F4CA{perc_on_active_val}%\n'
                    else:
                        perc_on_active_val_msg = ""
                    active_nominators_w_emoji = f'{active_nominators} \U00002696' if active_nominators > 256 else active_nominators
                    nom_percentile = info_current_era["nom_percentile"]
                    nom_position = info_current_era["nom_pos"]
                    emoji_oversubs = "" if nom_position <= 256 else f'\U00002757'
                    emoji_pos = add_emoji_position(nom_percentile)
                    nom_pos_per = f'{" "*8}\U0001F5F3{total_nominators} / {active_nominators_w_emoji}\n' \
                                  f'{" "*8}\U0001F3C5{nom_position}º{emoji_oversubs} top {nom_percentile}% {emoji_pos}\n' \
                                  f'{perc_on_active_val_msg}\n'
                else:
                    nom_pos_per = f'{" "*8}{total_nominators}\n'
            else:
                commission = "??"
                nom_pos_per = ""
            emoji_status = add_emoji_status(current_status)
            # Ask if the validator was slashed
            to_print = to_print + f'{emoji_status}> {identity_val} \U0001F9FE{commission}%:\n{nom_pos_per}'
    else:
        to_print = f'Address not nominating for the current era ({era_index})'

    # Add slahed info regardless of the current status
    if slashed_info:
        to_print = to_print + slashed_info
    return f'{to_print}\n/start'


def val_was_slashed(validator, validators_info):
    msj = ""
    if validators_info[validator].get("slashed"):
        slashed_era = validators_info[validator]["slashed"]
        msj = msj + f'\U0001F4A9 Validator {short_addr(validator)} slashed on era {slashed_era}\n'
    return msj


def nom_was_slashed(substrate, all_validators, nom):
    slashed_vals = {k: v for k, v in all_validators.items() if v.get("slashed")}
    msj = ""
    if slashed_vals:
        for val in slashed_vals.values():
            slashed_era = val["slashed"]
            if nom in val["era_info"][slashed_era]["nominators"]:
                amount = val["era_info"][slashed_era]["slashing"][nom]
                msj = msj + f'\U0001F52A\U0001FA78 Slashed {amount} {substrate.token_symbol} on era {slashed_era}'
    return msj


def add_order(status):
    if status == "Staked":
        order = 0
    elif status == "Active":
        order = 1
    elif status == "Waiting":
        order = 2
    else:
        order = 3
    return order


def get_active_nominated(validators_info, nom, era_index):
    active_noms = {val: stk["era_info"][era_index]["nominators"][nom] for
                   val, stk in validators_info.items()
                   if validators_info[val]["era_info"].get(era_index) and
                   validators_info[val]["era_info"][era_index].get("nominators") and
                   nom in validators_info[val]["era_info"][era_index]["nominators"]}
    currently_staking = sum(active_noms.values())
    full_dict = {"active_noms": active_noms, "currently_staking": currently_staking}
    return full_dict


def get_past_staking_rewards(validators_info, nom, past_era):
    past_active_nom_full = get_active_nominated(validators_info, nom, past_era)
    past_total_staked = past_active_nom_full["currently_staking"]
    past_active_noms = past_active_nom_full["active_noms"]
    past_rewards = 0
    for validator, staked_with_val in past_active_noms.items():
        val_info = validators_info[validator]["era_info"][past_era]
        prct_of_nom = staked_with_val/float(val_info["total_stake"])
        nom_rewarded = float(val_info["token_rewarded"]) * float(prct_of_nom)
        fee = 1-(float(val_info["commission"])/100)
        nom_rewarded_minus_fee = nom_rewarded * fee
        past_rewards += nom_rewarded_minus_fee
    return past_rewards, past_total_staked
