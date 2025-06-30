import asyncio
import json
import websockets
import requests
import time
import hashlib
import hmac
import random
from hashlib import sha256
import proto
import reading_config

config=reading_config.read_config()


list_raw=[]

def add_raw(time,username,msg,cmd,admin) :
    global list_raw
    my_dict={"time":time,"username":username,"message":msg,"cmd":cmd,"admin":admin}
    list_raw.append(my_dict)
    with open("logs\\todo_raw.json", "w", encoding='utf-8') as f:
        json.dump(list_raw, f, ensure_ascii=False, indent=4)

class BiliClient:
    def __init__(self, idCode, appId, key, secret, host):
        self.idCode = idCode
        self.appId = appId
        self.key = key
        self.secret = secret
        self.host = host
        self.gameId = ''
        pass

    # 事件循环
    def run(self):
        loop = asyncio.get_event_loop()
        # 建立连接
        websocket = loop.run_until_complete(self.connect())
        tasks = [
            # 读取信息
            asyncio.ensure_future(self.recvLoop(websocket)),
            # 发送心跳
            asyncio.ensure_future(self.heartBeat(websocket)),
             # 发送游戏心跳
            asyncio.ensure_future(self.appheartBeat()),
        ]
        loop.run_until_complete(asyncio.gather(*tasks))

    # http的签名
    def sign(self, params):
        key = self.key
        secret = self.secret
        md5 = hashlib.md5()
        md5.update(params.encode())
        ts = time.time()
        nonce = random.randint(1, 100000)+time.time()
        md5data = md5.hexdigest()
        headerMap = {
            "x-bili-timestamp": str(int(ts)),
            "x-bili-signature-method": "HMAC-SHA256",
            "x-bili-signature-nonce": str(nonce),
            "x-bili-accesskeyid": key,
            "x-bili-signature-version": "1.0",
            "x-bili-content-md5": md5data,
        }

        headerList = sorted(headerMap)
        headerStr = ''

        for key in headerList:
            headerStr = headerStr + key+":"+str(headerMap[key])+"\n"
        headerStr = headerStr.rstrip("\n")

        appsecret = secret.encode()
        data = headerStr.encode()
        signature = hmac.new(appsecret, data, digestmod=sha256).hexdigest()
        headerMap["Authorization"] = signature
        headerMap["Content-Type"] = "application/json"
        headerMap["Accept"] = "application/json"
        return headerMap

    # 获取长连信息
    def getWebsocketInfo(self):
        postUrl = f"{self.host}/v2/app/start"
        params = json.dumps({"code": self.idCode, "app_id": self.appId})  # 使用 json.dumps 更安全
        headerMap = self.sign(params)
        try:
            r = requests.post(postUrl, headers=headerMap, data=params, verify=False)
            data = r.json()  # 直接使用 r.json() 替代 json.loads(r.content)
            #print(data)
            #print("114514")

            # 校验 API 响应状态码
            if data.get('code') != 0:
                raise ValueError(f"API Error: {data.get('message')} (code={data.get('code')})")

            # 安全访问嵌套字段
            data_body = data.get('data', {})
            self.gameId = str(data_body.get('game_info', {}).get('game_id', ''))

            websocket_info = data_body.get('websocket_info', {})
            wss_links = websocket_info.get('wss_link', [])
            auth_body = websocket_info.get('auth_body', '')

            if not wss_links:
                raise ValueError("未获取到 WebSocket 地址")
            return wss_links[0], auth_body
        except Exception as e:
            print(f"获取 WebSocket 信息失败: {e}")
            raise
    async def appheartBeat(self):
        while True:
            await asyncio.ensure_future(asyncio.sleep(20))
            postUrl = "%s/v2/app/heartbeat" % self.host
            params = '{"game_id":"%s"}' % (self.gameId)
            headerMap = self.sign(params)
            r = requests.post(url=postUrl, headers=headerMap,
                          data=params, verify=False)
            data = json.loads(r.content)
            print("[BiliClient] send appheartBeat success")


    # 发送鉴权信息
    async def auth(self, websocket, authBody):
        req = proto.Proto()
        req.body = authBody
        req.op = 7
        await websocket.send(req.pack())
        buf = await websocket.recv()
        resp = proto.Proto()
        resp.unpack(buf)
        respBody = json.loads(resp.body)
        if respBody["code"] != 0:
            print("auth 失败")
        else:
            print("auth 成功")

    # 发送心跳
    async def heartBeat(self, websocket):
        while True:
            await asyncio.ensure_future(asyncio.sleep(20))
            req = proto.Proto()
            req.op = 2
            await websocket.send(req.pack())
            print("[BiliClient] send heartBeat success")

    # 读取信息
    async def recvLoop(self, websocket):
        print("[BiliClient] run recv...")
        #list_raw = manager.get_list()
        while True:
            try:

                recvBuf = await websocket.recv()
                resp = proto.Proto()
                resp.unpack(recvBuf)  # 解析原始数据到 Proto 对象

                # 检查 body 是否有效
                if not resp.body:
                    print("消息体为空，跳过处理")
                    continue

                try:
                    # 尝试解析 JSON
                    resp_data = json.loads(resp.body)
                except json.JSONDecodeError:
                    print(f"JSON 解析失败，原始内容: {resp.body}")
                    continue

                # 安全访问字段
                cmd = resp_data.get("cmd", "")
                data_body = resp_data.get("data", {})

                print(f"收到指令: {cmd}")

                if cmd == "LIVE_OPEN_PLATFORM_DM" and data_body.get('dm_type',1)==0:
                    msg = data_body.get("msg", "")
                    uname = data_body.get("uname", "匿名用户")
                    timestamp = time.time()

                    add_raw(timestamp,data_body.get("uname","unkown"),data_body.get("msg",""),cmd,data_body.get('is_admin',0))

                    print(f"捕获弹幕: {uname} -> {msg}")

                if cmd == "LIVE_OPEN_PLATFORM_SEND_GIFT":
                    msg =data_body.get("gift_name",'null')
                    uname=data_body.get('uname',"匿名")
                    timestamp=time.time()
                    add_raw(timestamp,uname,msg,cmd,0)

                if cmd =="LIVE_OPEN_PLATFORM_LIVE_ROOM_ENTER" :
                    uname=data_body.get("uname",'匿名')
                    timestamp=time.time()
                    add_raw(timestamp,uname,"",cmd,0)

                if cmd == "LIVE_OPEN_PLATFORM_LIKE" :
                    uname=data_body.get('uname','匿名')
                    timestamp=time.time()
                    count=data_body.get("like_count",0)
                    add_raw(timestamp,uname,count,cmd,0)

                if cmd == "LIVE_OPEN_PLATFORM_GUARD" :
                    uname= data_body.get('user_info','').get("uname",'')
                    timestamp=time.time()
                    type= data_body.get("guard_level",0)
                    add_raw(timestamp,uname,type,cmd,0)

            except websockets.exceptions.ConnectionClosed:
                print("WebSocket 连接已关闭")
                break
            except Exception as e:
                print(f"处理消息时发生异常: {e}")

    # 建立连接
    async def connect(self):
        addr, authBody = self.getWebsocketInfo()
        #(addr, authBody)
        websocket = await websockets.connect(addr)
        # 鉴权
        await self.auth(websocket, authBody)
        return websocket

    def __enter__(self):
        print("[BiliClient] enter")

    def __exit__(self, type, value, trace):
        # 关闭应用
        postUrl = "%s/v2/app/end" % self.host
        params = '{"game_id":"%s","app_id":%d}' % (self.gameId, self.appId)
        headerMap = self.sign(params)
        r = requests.post(url=postUrl, headers=headerMap,
                          data=params, verify=False)
        print("[BiliClient] end app success", params)


if __name__ == '__main__':

    try:
        cli = BiliClient(
            idCode=config['bili_config']['bili_idcode'],  # 主播身份码
            appId=config['bili_config']['bili_appid'],  # 应用id
            key=config['bili_config']['bili_key'],  # access_key
            secret=config['bili_config']['bili_key_secret'],  # access_key_secret
            host="https://live-open.biliapi.com") # 开放平台 (线上环境)
        with cli:
            cli.run()
    except Exception as e:
        print("err", e)