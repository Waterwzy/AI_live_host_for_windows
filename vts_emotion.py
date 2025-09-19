import asyncio
import pyvts
import random
import time
import os
from logging_config import app_logger

# 插件信息配置
PLUGIN_INFO = {
    "plugin_name": "vts emotion",
    "developer": "Waterwzy",
    "authentication_token_path": "./vts_token.txt"  # Token 存储文件
}


async def emotion_main():
    """触发随机情感（基于文件token管理）"""
    vts = None
    try:
        # 创建VTS实例
        vts = pyvts.vts(plugin_info=PLUGIN_INFO)

        # 连接到VTS
        await vts.connect()

        # 检查token文件是否存在
        token_file_path = PLUGIN_INFO["authentication_token_path"]

        if os.path.exists(token_file_path):
            # 如果token文件存在，直接进行认证
            try:
                await vts.request_authenticate()  # 使用文件中的token进行认证
                app_logger.info("Successfully authenticated with existing token")
            except Exception as auth_error:
                app_logger.warning("Token authentication failed, getting new token: %s", auth_error)
                # 认证失败，获取新token
                await vts.request_authenticate_token()  # 获取新token
                await vts.request_authenticate()  # 使用新token认证
        else:
            # 如果没有token文件，获取新token
            await vts.request_authenticate_token()  # 获取新token
            await vts.request_authenticate()  # 使用新token认证

        # 请求热键列表
        response_data = await vts.request(vts.vts_request.requestHotKeyList())

        # 检查响应是否包含预期的数据
        if 'data' not in response_data or 'availableHotkeys' not in response_data['data']:
            app_logger.error("Invalid response format from VTS: %s", response_data)
            await vts.close()
            return

        hotkey_list = []
        for hotkey in response_data['data']['availableHotkeys']:
            hotkey_list.append(hotkey['name'])

        # 随机选择一个热键
        if hotkey_list:
            random.seed(time.time())
            key_num = random.randint(0, len(hotkey_list) - 1)

            # 发送热键触发请求
            send_hotkey_request = vts.vts_request.requestTriggerHotKey(hotkey_list[key_num])
            await vts.request(send_hotkey_request)  # 发送请求播放情感
            app_logger.info("Triggered emotion: %s", hotkey_list[key_num])
        else:
            app_logger.warning("No hotkeys available")

    except Exception as e:
        app_logger.error("Error in vts emotion: %s", e)
    finally:
        # 确保连接被关闭
        if vts is not None:
            try:
                await vts.close()
            except Exception as close_error:
                app_logger.warning("Error closing VTS connection: %s", close_error)