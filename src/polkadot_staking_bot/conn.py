from substrateinterface import SubstrateInterface
import urllib.request
import json
import pickle


def init_substrate():
    # Add other networks when fixing the storage of variables. Not complicated, just do it!
    # substrate = SubstrateInterface(url="wss://kusama-rpc.polkadot.io/")
    substrate = SubstrateInterface(url="wss://rpc.polkadot.io")
    return substrate


def get_active_era(substrate):
    era_index = substrate.query(
        module='Staking',
        storage_function='ActiveEra'
        ).value["index"]
    return era_index


def retrieve_ss58_registry():
    registry_url = "https://raw.githubusercontent.com/paritytech/ss58-registry/main/ss58-registry.json"
    with urllib.request.urlopen(registry_url) as url:
        json_decoded = url.read().decode()
        json_file = json.loads(json_decoded)
        registry_dict = {reg["prefix"]: reg["network"] for reg in json_file["registry"]}

    with open("./src/data/ss58_registry_dict.pkl", 'wb') as output_data:
        pickle.dump(registry_dict, output_data)
