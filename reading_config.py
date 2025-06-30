import json
import os
def read_config() :
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    
    try:
        with open(config_path, 'r',encoding='utf-8') as config_file:
            return json.load(config_file)
    except Exception as e:
        print("error,",e)
    return