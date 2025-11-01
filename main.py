import subprocess
import time
import asyncio
import aiohttp
import json
import reading_config
from logging_config import app_logger

config = reading_config.read_config()

sing_list = config['live_config']['live_sing_list']
dmcount = []#key:user,count

# 异步过滤器访问
async def requestds(session, question):
    retry = 0
    while retry < config['filter_config']['filter_maxitry']:
        try:
            headers = {
                "Authorization": f"Bearer {config['filter_config']['filter_key']}",  # 使用 Bearer Token
                "Content-Type": "application/json"  # 指定请求体类型为 JSON
            }
            async with session.post(
                url=f"{config['filter_config']['filter_baseurl']}/chat/completions",
                json={
                    "model": config['filter_config']['filter_model'],
                    "messages": question,
                    "stream": False
                },
                headers=headers,
                timeout=config['filter_config']['filter_timeout']
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise Exception(f"HTTP error: {response.status}")
        except Exception as e:
            app_logger.error(f"filter error as {e} retrying...")
            retry += 1

    raise TimeoutError

# command 列表添加
def add_list(command_type, msg, command_user, time):
    global processlist, raw_list, listnow, todo_list
    todo_list[listnow]['type'] = command_type
    todo_list[listnow]["messages"] = msg
    todo_list[listnow]['user'] = command_user
    todo_list[listnow]['time'] = time  # 注意！添加消息在这里！
    todo_list.append({"type": '0', "messages": '0', "user": 'null', "time": 0})
    with open("logs\\command.json", 'w', encoding='utf-8') as f:
        json.dump(todo_list, f, ensure_ascii=False, indent=4)
    listnow += 1
    return

# 判断是否是合法的游戏指令
def legal_game_command(text):
    if not ('A' <= text[0] <= 'J' or 'a' <= text[0] <= 'j'):
        return None
    ordx = ord(text[0]) - ord('A') + 1 if 'A' <= text[0] <= 'J' else ord(text[0]) - ord('a') + 1
    if len(text) >= 4 or len(text) <= 1:
        return None
    if len(text) == 2:
        if '1' <= text[1] <= '9':
            return ordx, int(text[1])
        else:
            return None
    if len(text) == 3:
        if text[1:3] == '10':
            return ordx, 10
        else:
            return None
    return None

#如果不是合法的指令，在livetext中输出权限不够的提示
def not_legal_command(mode,username,need_command):
    global dmcount
    for user in dmcount:
        if user['user'] == username:
            with open('logs\\livetext.txt', 'a+', encoding='utf-8') as f:
                print(username+mode+'弹幕数量不够喵，还需要'+str(need_command-user['count']),file=f)
                return  None
    with open('logs\\livetext.txt', 'a+', encoding='utf-8') as f:
        print(username+mode+'弹幕数量不够喵，还需要'+str(need_command),file=f)
    return None

async def main():
    global processlist, raw_list, listnow, todo_list
    process_llm = subprocess.Popen(['python', "llm.py"]  , stderr= subprocess.PIPE , text = True )
    process_ws = subprocess.Popen(['python', "ws.py"]  , stderr= subprocess.PIPE , text = True )

    listnow = 0
    processlist = 0
    todo_list = []
    game_list = []

    nowgame = 0
    game_user = ''
    game_command_last_time = 0
    todo_list.append({"type": '0', "messages": '0', "user": "null"})
    prompt = '\n'.join(config['filter_config']['filter_prompt'])
    message = [{"role": "system", "content": prompt}, {}]

    # 增加新的变量来管理并发过滤任务
    filter_tasks = []      # 收集 awaitable 的 requestds 调用
    danmaku_to_process = [] # 收集需要过滤的弹幕的原始信息

    with open("logs\\command.json", 'w', encoding='utf-8') as f:
        json.dump(todo_list, f, ensure_ascii=False, indent=4)
    with open("logs\\todo_raw.json", "w", encoding='utf-8') as f:
        json.dump([], f, ensure_ascii=False, indent=4)

    #await emotion_init()

    async with aiohttp.ClientSession() as session:
        while True:
            # 子进程异常关闭监测
            if process_ws.poll() is not None:
                err_message = process_ws.stderr.read() if process_ws.stderr else 'N/A'
                print(f"!!!CIRTICAL!!! ws.py has STOPPED!!RETURN INFORMATION:{err_message}")
                app_logger.critical(f"ws停止 with return code：{process_ws.returncode}.restarting...")
                process_ws = subprocess.Popen(['python', "ws.py"], stderr=subprocess.PIPE  , text=True)

            if process_llm.poll() is not None:
                err_message = process_llm.stderr.read() if process_llm.stderr else 'N/A'
                print(f"!!!CRITICAL!!! llm.py has STOPPED!!!RETURN INFORMATION:{err_message}")
                app_logger.critical(f"process停止，with return code{process_llm.returncode}.restarting...")
                process_llm = subprocess.Popen(['python', "llm.py"], stderr=subprocess.PIPE , text=True)
            try:
                if process_game.poll() is not None:
                    # print("game停止，游戏重置")
                    nowgame = False
            except Exception:
                pass
            try:
                with open("logs\\todo_raw.json", "r", encoding='utf-8') as f:
                    raw_list = json.load(f)
            except Exception as e:
                app_logger.warning("fail to read the raw!")
                await asyncio.sleep(1)
                continue
            if nowgame:
                if time.time() - game_command_last_time > config['beta_config']['beta_gamemode_timeout']:
                    nowgame = 0
                    try:
                        process_game.kill()
                        app_logger.info("game killed cause of timeout")
                    except Exception as e:
                        app_logger.warning("fail to kill the game!")
            while len(raw_list) > processlist:
                
                if nowgame and raw_list[processlist].get('username') == game_user and (
                    legal_game_command(raw_list[processlist].get('message')) is not None):
                    app_logger.info('game message get!')
                    text = raw_list[processlist].get('message')
                    game_dict = {"cmd": "down", "message": legal_game_command(text)}
                    game_list.append(game_dict)
                    with open("logs\\game.json", "w", encoding='utf-8') as f:
                        json.dump(game_list, f, ensure_ascii=False, indent=4)
                    game_command_last_time = time.time()
                # 简单命令的处理（进入直播间，送礼，点赞，大航海）
                elif raw_list[processlist].get('cmd', 'null') == "LIVE_OPEN_PLATFORM_LIVE_ROOM_ENTER":
                    with open("logs\\livetext.txt", 'a+', encoding='utf-8') as f:
                        print("欢迎 " + raw_list[processlist]['username'] + " 喵", file=f)

                elif raw_list[processlist].get('cmd', 'null') == 'LIVE_OPEN_PLATFORM_SEND_GIFT':
                    with open("logs\\livetext.txt", 'a+', encoding='utf-8') as f:
                        print("感谢 " + raw_list[processlist]['username'] + " 投喂的" + raw_list[processlist][
                            'message'] + "谢谢喵", file=f)
                    add_list('gift',raw_list[processlist]['message'],raw_list[processlist]['username'],0 )

                elif raw_list[processlist].get('cmd', 'null') == 'LIVE_OPEN_PLATFORM_LIKE':
                    with open("logs\\livetext.txt", 'a+', encoding='utf-8') as f:
                        print("感谢 " + raw_list[processlist]['username'] + " 的 " + str(
                            raw_list[processlist]['message']) + " 个喜欢喵", file=f)
                    add_list('like',raw_list[processlist]['message'],raw_list[processlist]['username'],0)

                elif raw_list[processlist].get('cmd', 'null') == 'LIVE_OPEN_PLATFORM_GUARD':
                    lv = raw_list[processlist].get('message', -1)
                    if lv == 1:
                        gtype = '总督'
                    elif lv == 2:
                        gtype = '提督'
                    else:
                        gtype = '舰长'
                    with open('logs\\livetext.txt', 'a+', encoding='utf-8') as f:
                        print("谢谢 " + raw_list[processlist]['username'] + '的' + gtype + "\n谢谢老板老板大气喵",file=f)

                # 弹幕逻辑处理
                elif raw_list[processlist].get("cmd", 'null') == 'LIVE_OPEN_PLATFORM_DM':
                    message_content = raw_list[processlist].get("message", "")
                    username = raw_list[processlist].get("username", "匿名")
                    # 移除上下文，判定是否为房管或主播鉴权
                    if raw_list[processlist].get('message', '') == 'remtext' and (
                            raw_list[processlist].get('admin', 0) == 1 or raw_list[processlist].get("username",
                                                                                                    'unknown') ==
                            config['live_config']['live_upid']):
                        add_list('rem', '', '', 0)
                    # 翻唱命令
                    elif message_content.startswith("翻唱 "):
                        singname = message_content[3:]
                        flag = 0
                        # 检查用户权限
                        for user in dmcount:
                            if user['user'] == username and user['count'] >= config['live_config']['live_sing_count']:
                                user['count'] -= config['live_config']['live_sing_count']
                                flag = 1
                                break
                        if flag == 0 and config['live_config']['live_sing_count']:
                            processlist += 1
                            not_legal_command('翻唱',username,config['live_config']['live_sing_count'])
                            continue
                        # 添加翻唱请求
                        for sings in sing_list:
                            if singname == str(sings['num']) or singname == sings['name']:
                                add_list('aising', sings['name'], '', 0)
                                app_logger.info("翻唱请求已添加！")
                                break
                    elif raw_list[processlist].get('message', '')[0] == '#' or raw_list[processlist].get('message','')[0:3]=='点歌 ':
                        pass
                    # 点歌命令
                    elif message_content.startswith("点歌 "):
                        pass
                    # 游戏代码集成
                    elif raw_list[processlist].get('message', '') == "game" and config['beta_config']['beta_open_gamemode']:
                        # 我不知道为什么鉴权要写这么长
                        if nowgame == 1:
                            processlist += 1
                            continue
                        flag = 0
                        for user in dmcount:
                            if user['user'] == raw_list[processlist]['username']:
                                if user['count'] >= config['beta_config']['beta_gamemode_danmaku']:
                                    user["count"] -= config['beta_config']['beta_gamemode_danmaku']
                                    flag = 1
                                    break
                        if flag == 0 and config['beta_config']['beta_gamemode_danmaku']:
                            processlist += 1
                            not_legal_command('游戏',username,config['beta_config']['beta_gamemode_danmaku'])
                            continue
                        # 开始游戏了
                        nowgame = True
                        game_user = raw_list[processlist]['username']
                        game_command_last_time = time.time()
                        game_list = []
                        add_dict = {'cmd': 'start', 'message': game_user}
                        game_list.append(add_dict)
                        app_logger.info(f"game start:\nplayer:{game_user}" )
                        with open("logs\\game.json", "w", encoding='utf-8') as f:
                            json.dump(game_list, f, ensure_ascii=False, indent=4)
                        process_game = subprocess.Popen(['python', "game\\main.py"],stderr= subprocess.PIPE ,text=True)

                    # 普通弹幕处理
                    else:
                        try:
                            with open("logs\\text.json", 'r', encoding='utf-8') as f:
                                mystr = f.read()
                            
                            # 准备 message for requestds
                            message = [{"role": "system", "content": prompt}, 
                                        {"role": "user", "content": f"{mystr}\nnew_danmaku：{username}:{message_content}"}]
                                
                                # 收集任务和原始弹幕信息
                            filter_tasks.append(requestds(session, message))
                            danmaku_to_process.append({
                                    "message_content": message_content,
                                    "username": username,
                                    "time": raw_list[processlist].get("time", 0),
                                    "raw_index": processlist # 记录原始索引，方便后续更新 dmcount
                            })
                        except Exception as e:
                            app_logger.error("fail to read text")
                            await asyncio.sleep(1)
                            continue

                processlist += 1

            if filter_tasks:
                app_logger.info(f"开始并发处理 {len(filter_tasks)} 个弹幕过滤请求...")
                # 并发执行所有收集到的过滤请求
                results = await asyncio.gather(*filter_tasks, return_exceptions=True)

                for i, response in enumerate(results):
                    original_dm = danmaku_to_process[i]
                    username = original_dm['username']
                    message_content = original_dm['message_content']
                    
                    if isinstance(response, Exception):
                        # 处理过滤失败或超时的情况
                        app_logger.error(f"Error processing danmaku from {username}: {response}")
                        continue # 跳过对这个弹幕的进一步处理
                    
                    try:
                        content = response['choices'][0]['message']['content'].strip()
                        if content == 'process':
                            # 添加弹幕到处理列表 (DM)
                            flag = 0
                            for user in dmcount:
                                if user['user'] == username:
                                    flag = 1
                                    user['count'] += 1
                                    break
                            if flag == 0:
                                dmcount.append({"user": username, "count": 1})
                                
                            add_list("DM", message_content, username, original_dm["time"])
                            app_logger.info(f"弹幕已处理！内容:{message_content}")
                        else:
                            app_logger.info(f"弹幕被过滤！内容:{message_content}")
                            # 可选：打印过滤原因
                            # app_logger.info(response['choices'][0]['message']['reasoning_content'])
                            
                    except (KeyError, IndexError, TypeError) as e:
                        app_logger.error(f"Error parsing filter response for {username}: {e}")
                
                # 清空任务列表，准备下一批
                filter_tasks = []
                danmaku_to_process = []

            if len(raw_list) <= processlist:
                await asyncio.sleep(1) # 暂停，等待 ws.py 写入新数据


if __name__ == '__main__':
    asyncio.run(main())