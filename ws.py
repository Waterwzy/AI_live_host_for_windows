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
from logging_config import app_logger
import aiohttp

config=reading_config.read_config()

list_raw=[]

def add_raw(time,username,msg,cmd,admin) :
    global list_raw
    my_dict={"time":time,"username":username,"message":msg,"cmd":cmd,"admin":admin}
    list_raw.append(my_dict)
    with open("logs\\todo_raw.json", "w", encoding='utf-8') as f:
        json.dump(list_raw, f, ensure_ascii=False, indent=4)

class BiliClient:
    def __init__(self, idCode, appId, key, secret, host,session):
        self.idCode = idCode
        self.appId = appId
        self.key = key
        self.secret = secret
        self.host = host
        self.gameId = ''
        self.session = session
        pass

    # 事件循环
    async def run_async(self):

        # 建立连接
        websocket = await self.connect()
        tasks = [
            # 读取信息
            asyncio.ensure_future(self.recvLoop(websocket)),
            # 发送心跳
            asyncio.ensure_future(self.heartBeat(websocket)),
             # 发送游戏心跳
            asyncio.ensure_future(self.appheartBeat()),
        ]
        await asyncio.gather(*tasks)

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
    async def getWebsocketInfo(self):
        postUrl = f"{self.host}/v2/app/start"
        params = json.dumps({"code": self.idCode, "app_id": self.appId})  # 使用 json.dumps 更安全
        headerMap = self.sign(params)
        try:

            # 使用 self.session (aiohttp) 发送异步请求
            async with self.session.post(
                postUrl, 
                headers=headerMap, 
                data=params, 
                verify_ssl=False # 对应 requests 里的 verify=False
            ) as response:
                
                if response.status != 200:
                    raise Exception(f"HTTP error: {response.status}")
                    
                data = await response.json() # <--- 异步解析 JSON

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
            app_logger.error(f"获取 WebSocket 信息失败: {e}")
            raise
    async def appheartBeat(self):
        while True:
            await asyncio.sleep(20)
            postUrl = "%s/v2/app/heartbeat" % self.host
            params = '{"game_id":"%s"}' % (self.gameId)
            headerMap = self.sign(params)
            try:
                # 使用 self.session (aiohttp) 发送异步请求
                async with self.session.post(
                    url=postUrl, 
                    headers=headerMap,
                    data=params, 
                    verify_ssl=False
                ) as response:
                    # 确保等待响应的 JSON 解析
                    data = await response.json() 
                    
                    if response.status == 200 and data.get('code') == 0:
                        app_logger.info("[BiliClient] send appheartBeat success")
                    else:
                        app_logger.warning(f"[BiliClient] appheartBeat failed. Status: {response.status}, Code: {data.get('code', 'N/A')}")
                        
            except Exception as e:
                app_logger.error(f"[BiliClient] appheartBeat encountered an error: {e}")


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
            app_logger.error("auth 失败")
        else:
            app_logger.info("auth 成功")

    # 发送心跳
    async def heartBeat(self, websocket):
        while True:
            await asyncio.ensure_future(asyncio.sleep(20))
            req = proto.Proto()
            req.op = 2
            await websocket.send(req.pack())
            app_logger.info("[BiliClient] send heartBeat success")

    # 读取信息
    async def recvLoop(self, websocket):
        app_logger.info("[BiliClient] run recv...")
        #list_raw = manager.get_list()
        while True:
            try:

                recvBuf = await websocket.recv()
                resp = proto.Proto()
                resp.unpack(recvBuf)  # 解析原始数据到 Proto 对象

                # 检查 body 是否有效
                if not resp.body:
                    app_logger.debug("消息体为空，跳过处理")
                    continue

                try:
                    # 尝试解析 JSON
                    resp_data = json.loads(resp.body)
                except json.JSONDecodeError:
                    app_logger.debug(f"JSON 解析失败，原始内容: {resp.body}")
                    continue

                # 安全访问字段
                cmd = resp_data.get("cmd", "")
                data_body = resp_data.get("data", {})

                app_logger.info(f"收到指令: {cmd}")
                #针对不同命令的添加，对于相关命令不重要的字段直接省去
                if cmd == "LIVE_OPEN_PLATFORM_DM" and data_body.get('dm_type',1)==0:
                    msg = data_body.get("msg", "")
                    uname = data_body.get("uname", "匿名用户")
                    timestamp = time.time()

                    add_raw(timestamp,data_body.get("uname","unkown"),data_body.get("msg",""),cmd,data_body.get('is_admin',0))

                    app_logger.info(f"捕获弹幕: {uname} -> {msg}")

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
                app_logger.error("WebSocket 连接已关闭")
                break
            except Exception as e:
                app_logger.error(f"处理消息时发生异常: {e}")

    # 建立连接
    async def connect(self):
        addr, authBody = await self.getWebsocketInfo()
        #(addr, authBody)
        websocket = await websockets.connect(addr)
        # 鉴权
        await self.auth(websocket, authBody)
        return websocket

    def __enter__(self):
        app_logger.info("[BiliClient] enter")

    def __exit__(self, type, value, trace):
        # 关闭应用
        postUrl = "%s/v2/app/end" % self.host
        params = '{"game_id":"%s","app_id":%d}' % (self.gameId, self.appId)
        headerMap = self.sign(params)
        r = requests.post(url=postUrl, headers=headerMap,
                          data=params, verify=False)
        app_logger.warning("[BiliClient] end app success"+ params)


# 异步启动函数 (保持不变)
async def start_client():
    # 在最外层创建 aiohttp session，并传入 BiliClient
    async with aiohttp.ClientSession() as session:
        cli = BiliClient(
            idCode=config['bili_config']['bili_idcode'],
            appId=config['bili_config']['bili_appid'],
            key=config['bili_config']['bili_key'],
            secret=config['bili_config']['bili_key_secret'],
            host="https://live-open.biliapi.com",
            session=session # 传入异步 session
        )
        cli.__enter__() # 手动调用 enter 逻辑
        try:
            await cli.run_async() # 运行异步任务
        finally:
            cli.__exit__(None, None, None) # 确保退出时执行 app_end 逻辑

if __name__ == '__main__':
    try:
        # 运行异步启动函数
        asyncio.run(start_client())
    except Exception as e:
        print("err", e)