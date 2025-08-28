import asyncio
import pyvts
import random
import time
async def emotion_main():
    try:
        vts=pyvts.vts()
        await vts.connect()
        await vts.request_authenticate_token()  # get token
        await vts.request_authenticate()  # use token
        response_data = await vts.request(vts.vts_request.requestHotKeyList())
        hotkey_list = []
        for hotkey in response_data['data']['availableHotkeys']:
            hotkey_list.append(hotkey['name'])
        random.seed(time.time())
        key_num=random.randint(0,len(hotkey_list)-1)
        send_hotkey_request = vts.vts_request.requestTriggerHotKey(hotkey_list[key_num])
        await vts.request(send_hotkey_request) # send request to play emotion
        await vts.close()
    except Exception as e:
        print("error in vts emotion:",e)
async def emotion_init():
    try:
        vts=pyvts.vts()
        await vts.connect()
        await vts.request_authenticate_token()
        await vts.request_authenticate()
        await vts.close()
        print("successfully connected to vts!")
    except Exception as e:
        print("error in init vts :",e)
