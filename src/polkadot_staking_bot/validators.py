import pickle
from os.path import exists
import logging

from utils import file_status, short_addr

def get_all_validators_commissions(substrate, era_index):
    """
    Obtiene todos los validadores (activos e inactivos)
    No acepta el parámetro de era, así que da los activos en el momento que se pide
    :param substrate: Conexión al RPC
    :return: Diccionario con estructura {val_address: {"era_info": {era: {"comission": float}}}}
    """
    run, all_validators = file_status(file='./src/data/all_validators_comm.pkl')

    if not run and all_validators:
        # Si el archivo es reciente (run == False) pero no tiene la era, se cambia a run = True
        eras_in_all_validators = all_validators[list(all_validators)[0]]["era_info"].keys()
        run = False if era_index in eras_in_all_validators else True

    if run:
        validators_1 = substrate.query_map(
            module='Staking',
            storage_function='Validators',
            page_size=1000
        )
        # Última key de la página anterior
        validators_2 = substrate.query_map(
            module='Staking',
            storage_function='Validators',
            start_key=validators_1.last_key,
            page_size=1000
        )
        all_validators_raw = validators_1.records + validators_2.records
        # Se guarda la comisión de la era actual en la era que se pide. WRONG!
        all_validators_current = {val[0].value: {"era_info": {era_index: {
            "commission": val[1].value["commission"] / 10000000}}} for val in all_validators_raw}
        all_validators.update(all_validators_current)
        with open('./src/data/all_validators_comm.pkl', 'wb') as output_data:
            pickle.dump(all_validators, output_data)

    return all_validators


def get_active_validators(substrate, era_index):
    """
    Obtiene la lista de validadores activos para la era proporcionada
    :param substrate: Conexión al RPC
    :param era_index: Era
    :return: Diccionario con formato {validator: {"total": int, "own": int, "others":{"who": int}}}
    """
    eras_stakers = substrate.query_map(
        module='Staking',
        storage_function='ErasStakers',
        page_size=300,
        params=[era_index]
    )
    validators_staking = {validator[0].value: validator[1].value for validator in eras_stakers.records}

    return validators_staking


def get_validators_info(substrate, nominators, era_index):
    """
    Obtener información sobre todos los validadores
    :param nominators:
    :param substrate: Conexión con RPC
    :param era_index: Era para la que se quiere información
    :return:
    """
    logger = logging.getLogger("polkadot_staking_bot")
    new_era = False
    if exists('./src/data/validators_info.pkl'):
        with open('./src/data/validators_info.pkl', 'rb') as input_data:
            all_validators = pickle.load(input_data)
        saved_eras = list(list(all_validators.values())[0]["era_info"].keys())
        if era_index in saved_eras:
            run = False
        else:
            logger.info(f'> Era {era_index} not saved...')
            new_era = True
            run = True
    else:
        logger.info(f'> No eras saved file. Creating a new one...')
        run = True

    to_units = 10 ** substrate.token_decimals
    if run:
        # Sólo se actualiza una vez por día cuando la era cambia

        all_validators_commission = get_all_validators_commissions(substrate, era_index)
        active_validators = get_active_validators(substrate, era_index)
        all_validators_status = add_status_stake(all_validators_current=all_validators_commission,
                                                 active_validators=active_validators,
                                                 to_units=to_units,
                                                 era_index=era_index)
        all_validators_current = count_nominators(nominators=nominators,
                                                  validators=all_validators_status,
                                                  era_index=era_index)

        if new_era:
            for validator in all_validators:
                # Un validador de eras pasadas no está en la actual
                if all_validators_current.get(validator):
                    # Si está, se actualiza con la info de la era actual
                    # Este update no borra eras pasadas??
                    all_validators[validator]["era_info"].update(all_validators_current[validator]["era_info"])
                else:
                    # Si no está, se añade
                    all_validators.update({validator: {"era_info": {era_index: {"status": "NOT A VALIDATOR"}}}})
        else:
            # No existe el pkl
            all_validators = all_validators_current

        try:
            all_validators = add_slashes(substrate, all_validators)
        except Exception as ex:
            logger.error(f'> {ex}')

        with open('./src/data/validators_info.pkl', 'wb') as output_data:
            pickle.dump(all_validators, output_data)

        logger.info(f'> Total Validators: {len(all_validators)}')

    return all_validators


def add_slashes(substrate, all_validators):
    unapplied_slashes = substrate.query_map(
        module='Staking',
        storage_function='UnappliedSlashes'
    )

    if unapplied_slashes.records:
        slashed_list = []
        slased_dict = {}
        for slash in unapplied_slashes:
            era = slash[0]
            slased_dict["era"] = era.value_object
            for val in slash[1]:
                slased_val = val["validator"]
                slased_dict["validator"] = slased_val.value_object
                nom_dict = {}
                for nom in val["others"]:
                    nom_dict[nom[0].value_object] = nom[1].value_object/(10**substrate.token_decimals)
                slased_dict["nominators"] = nom_dict
            slashed_list.append(slased_dict)

        for slashed in slashed_list:
            slashed_validator = slashed["validator"]
            slashed_era = slashed["era"]
            all_validators[slashed_validator].update({"slashed": slashed_era})
            all_validators[slashed_validator]["era_info"][slashed_era].update({"slashing": slashed["nominators"]})

    return all_validators


def count_nominators(nominators, validators, era_index):
    # Bucle para ver los validadores de cada nominador
    for nom in nominators:
        for val in nominators[nom]["validators_nominated"]:
            if val not in validators:
                validators[val] = {"era_info": {era_index: {"status": "NOT A VALIDATOR", "total_nominators": 0}}}
            if not validators[val]["era_info"][era_index].get("total_nominators"):
                validators[val]["era_info"][era_index]["total_nominators"] = 0
            validators[val]["era_info"][era_index]["total_nominators"] += 1
    return validators


def add_status_stake(all_validators_current, active_validators, to_units, era_index):
    # Recorre todos los validadores y le añade info en caso de estar activos para la era indicada
    for validator in all_validators_current:
        if all_validators_current[validator]["era_info"].get(era_index):
            all_validators_current[validator]["era_info"][era_index]["total_nominators"] = 0
            all_validators_current[validator]["era_info"][era_index]["status"] = "Waiting"
        else:
            all_validators_current.update({validator: {"era_info":
                                                           {era_index:
                                                                {"status": "Waiting", "total_nominators": 0}}}})

        if validator in active_validators:
            all_validators_current[validator]["era_info"][era_index]["status"] = "Active"
            total_stake = active_validators[validator]["total"] / to_units
            all_validators_current[validator]["era_info"][era_index]["total_stake"] = total_stake
            self_stake = active_validators[validator]["own"]
            all_validators_current[validator]["era_info"][era_index]["self_stake"] = self_stake / to_units
            others_stake = active_validators[validator]["total"] - active_validators[validator]["own"]
            all_validators_current[validator]["era_info"][era_index]["others_stake"] = others_stake / to_units
            others_og = active_validators[validator]["others"]
            others = {list(other.values())[0]: list(other.values())[1]/to_units for other in others_og}
            all_validators_current[validator]["era_info"][era_index]["nominators"] = others
            # Diferencia entre active_nominators y total_nominators?
            all_validators_current[validator]["era_info"][era_index]["active_nominators"] = len(others)
            all_validators_current[validator]["era_info"][era_index]["total_nominators"] = len(others)
    return all_validators_current


def add_token_rewarded(substrate, validators_info, era_index):
    logger = logging.getLogger("polkadot_staking_bot")

    try:
        to_units = 10 ** substrate.token_decimals
        past_era = era_index - 1

        # Token a repartir para esa era
        eras_validator_reward = substrate.query(module='Staking',
                                                storage_function='ErasValidatorReward',
                                                params=[past_era]
                                                ).value/to_units
        # Puntos totales e individuales repartidos para cada validador
        eras_reward_points = substrate.query(module='Staking',
                                             storage_function='ErasRewardPoints',
                                             params=[past_era]
                                             ).value

        # Tokens que le corresponden a cada validador según los puntos que consiguió respecto al total
        reward_tokens = {past_era: {val_points[0]: eras_validator_reward * (val_points[1] / eras_reward_points["total"]) for val_points in eras_reward_points["individual"]}}

        # Añadir los rewards a diccionario principal
        for val in reward_tokens[past_era]:
            if validators_info.get(val) and validators_info[val]["era_info"].get(past_era):
                validators_info[val]["era_info"][past_era]["token_rewarded"] = reward_tokens[past_era][val]

        return validators_info
    except Exception as ex:
        logger.error(f'> 227: {ex}')



def get_identity_info(substrate, addr):
    """
    Obtiene informacion de identidad de una dirección dada
    :param substrate: Conexión RPC
    :param addr: Dirección
    :return: Diccionario con formato {display_name: str, web: str, email: str, twitter: str, matrix: str}
    """
    og_identity = substrate.query(
        module='Identity',
        storage_function='SuperOf',
        params=[addr]
    )
    if og_identity.value:
        identity = og_identity.value[0]
        subtitle = f'/{og_identity.value[1]["Raw"]}' if og_identity.value[1].get("Raw") else ""
    else:
        identity = addr
        subtitle = ""

    identity_of = substrate.query(
        module='Identity',
        storage_function='IdentityOf',
        params=[identity]
    ).value

    info = {}
    display_name = f'{identity_of["info"]["display"]["Raw"]}{subtitle}' if identity_of else short_addr(addr)
    info["display_name"] = display_name
    info["stash"] = identity
    if identity_of:
        info["web"] = identity_of["info"]["web"].get("Raw") if not identity_of["info"]["web"].get("None") else None
        info["email"] = identity_of["info"]["email"].get("Raw") if not identity_of["info"]["email"].get(
            "None") else None
        info["twitter"] = identity_of["info"]["twitter"].get("Raw") if not identity_of["info"]["twitter"].get(
            "None") else None
        info["riot"] = identity_of["info"]["riot"].get("Raw") if not identity_of["info"]["riot"].get("None") else None
    else:
        info["web"] = info["email"] = info["twitter"] = info["riot"] = None

    return info
