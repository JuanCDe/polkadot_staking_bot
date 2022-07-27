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
    staked_by_nominator = get_staking_nominator(substrate, nom)
    past_reward = 0
    nominated = {}
    slashed_info = ""
    if staked_by_nominator and nom in all_nominators:
        validator_list = all_nominators[nom]["validators_nominated"]
        slashed_nominator_msj = nom_was_slashed(substrate, validators_info, nom)
        slashed_validator_msj = val_was_slashed(validator_list, validators_info)
        slashed_info = slashed_nominator_msj + slashed_validator_msj
        for validator in all_nominators[nom]["validators_nominated"]:
            if validators_info.get(validator):
                # Was slashed?
                nominated[validator] = validators_info.get(validator)
                past_era = era_index-1
                if validators_info[validator]["era_info"].get(past_era):
                    past_era_noms = validators_info[validator]["era_info"][past_era].get("nominators")
                    if past_era_noms and nom in past_era_noms:
                        past_era_status = "was_nominated"
                    else:
                        past_era_status = "was_not_nominated"
                else:
                    past_era_status = "no_info"
                if past_era_status == "was_nominated":
                    # Sólo si estaba dentro del set de nominadores activo!
                    prct_of_nom = staked_by_nominator/float(nominated[validator]["era_info"][past_era]["total_stake"])
                    nom_rewarded = float(nominated[validator]["era_info"][past_era]["token_rewarded"]) * float(prct_of_nom)
                    fee = 1-(float(nominated[validator]["era_info"][past_era]["commission"])/100)
                    nom_rewarded_minus_fee = nom_rewarded * fee
                    partial_past_reward = round(nom_rewarded_minus_fee, 4)
                    # En caso de que tuviera su stack repartido en varios validadores
                    past_reward += partial_past_reward

                status = validators_info[validator]["era_info"][era_index]["status"]

                if status == "Active":
                    staking_nominators = validators_info[validator]["era_info"][era_index]["nominators"]
                    status = "Nominated" if nom in staking_nominators else "Active"
                    nominated[validator]["era_info"][era_index]["status"] = status
                    prct_pos = get_pos_percentile(list(staking_nominators.values()), staked_by_nominator)
                    nominated[validator]["era_info"][era_index]["nom_pos"] = prct_pos["value_pos"]
                    nominated[validator]["era_info"][era_index]["nom_percentile"] = prct_pos["percentile_rounded"]
                    nominated[validator]["era_info"][era_index]["len_nominators"] = prct_pos["len_list"]
            else:
                status = "NOT A VALIDATOR"
                nominated.update({validator: {"era_info": {era_index: {"status": status}}}})

            nominated[validator]["identity_info"] = get_identity_info(substrate, validator)

            nominated[validator]["era_info"][era_index]["status_order"] = add_order(status)

    else:
        nominated = None
    result = {"nominated": nominated, "past_reward": past_reward, "slashed": slashed_info}
    return result


def get_nominating_summary(substrate, nominator_details, era_index, nom):
    nominated = nominator_details["nominated"]
    past_reward = nominator_details["past_reward"]
    slashed_info = nominator_details["slashed"]
    if nominated:
        nom_shorted = short_addr(nom)
        nom_link = f'[{nom_shorted}](https://polkadot.subscan.io/account/{nom})'
        staked = get_staking_nominator(substrate, nom)
        to_print = f'\U0001F449 {nom_link}\n' \
                   f'\U0001F4B0 past era ({era_index-1}) *{past_reward} {substrate.token_symbol}*\n\n' \
                   f'\U0001F4C5 current era *{era_index}*\n' \
                   f'\U0001F969 {round(staked, 3)} {substrate.token_symbol}\n\n'
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
                if current_status == "Active" or current_status == "Nominated":
                    active_nominators = info_current_era["active_nominators"]
                    # Se suma 1 si el validador no es el nominado ya que sería el supuesto de que formase parte de su lista
                    active_nominators = active_nominators+1 if current_status == "Active" else active_nominators
                    active_nominators_w_emoji = f'{active_nominators} \U00002696' if active_nominators > 256 else active_nominators
                    nom_percentile = info_current_era["nom_percentile"]
                    nom_position = info_current_era["nom_pos"]
                    emoji_oversubs = "" if nom_position <= 256 else f'\U00002757'
                    emoji_pos = add_emoji_position(nom_percentile)
                    nom_pos_per = f'{" "*8}\U0001F5F3{total_nominators}/{active_nominators_w_emoji}\n' \
                                  f'{" "*8}\U0001F3C5{nom_position}º{emoji_oversubs} top {nom_percentile}% {emoji_pos}\n\n'
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


def val_was_slashed(validator_list, validators_info):
    msj = ""
    for validator in validator_list:
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
    if status == "Nominated":
        order = 0
    elif status == "Active":
        order = 1
    elif status == "Waiting":
        order = 2
    else:
        order = 3
    return order
