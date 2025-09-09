from asyncio import create_task
from collections import deque
import aiohttp
import requests
import json
from pydub import AudioSegment
import os
from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
import winsound
from psutil import NoSuchProcess, AccessDenied
import time
import copy
import reading_config
import vts_emotion
import asyncio

config=reading_config.read_config()
message=[]

#调整进程音量 beta功能
def set_process_volume(process_name, target_volume):
    sessions = AudioUtilities.GetAllSessions()
    target_sessions = []
    # 第一步：安全收集需要调整音量的会话
    for session in sessions:
        try:
            if session.Process:
                proc_name = session.Process.name()
                if proc_name == process_name:
                    target_sessions.append(session)
        except (NoSuchProcess, AccessDenied, AttributeError):
            # 进程已终止、权限不足或属性不存在
            continue
    
    # 第二步：调整音量（减少进程中途退出的风险）
    for session in target_sessions:
        try:
            volume = session._ctl.QueryInterface(ISimpleAudioVolume)
            volume.SetMasterVolume(target_volume, None)
        except Exception as e:
            print(f"调整音量失败: {e}")

#llm的访问过程，兼容openai接口
async def request_firefly(session,question):
    retry=0
    payload={
        "model":config['llm_config']['llm_model'],
        "messages":question,
        "stream":False,
        "headless":1,
    }
    headers = {
        "Authorization":f"Bearer {config['llm_config']['llm_key']}",
        "Content-Type": "application/json"
    }
    while retry < config['llm_config']['llm_maxitry'] :
        try :
            async with session.post(
                url=f"{config['llm_config']['llm_baseurl']}/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=config['llm_config']['llm_timeout']
            )as response :
                if response.status == 200:
                    return await response.json()
                else :
                    raise Exception(f"HTTP error: {response.status}")
        except Exception as e:
            print("Error in llm:",e," retrying...")
            retry+=1
    raise TimeoutError

#tts函数，兼具输出音频流和文本功能，payload可以自己改
async def TTS(text):
    #mytime=0
    payload = {
        "text": text,
        "text_lang": "zh",
        "ref_audio_path": config['tts_config']['tts_ref_audio_path'],
        "aux_ref_audio_paths": [],
        "prompt_text": config['tts_config']['tts_prompt_text'],
        "prompt_lang": "zh",
        "top_k": 7,
        "top_p": 1,
        "temperature": 1.3,
        "text_split_method": "cut5",
        "batch_size": 20,
        "speed_factor": config["tts_config"]['tts_speed'],
        "ref_text_free": False,
        "split_bucket": True,
        "fragment_interval": 0.3,
        "seed": -1,
        "keep_random": True,
        "media_type": "wav",
        "streaming_mode": False,
        "parallel_infer": True,
        "repetition_penalty": 1.35,
        "frequency_penalty":0.5,
        "timeout":config['tts_config']['tts_timeout']
    }
    retry=0
    while retry <= config['tts_config']['tts_maxitry'] :
        try:
            response = requests.post(config['tts_config']['tts_baseurl'], json=payload)
            if response.status_code == 200 and 'audio/wav' in response.headers.get('Content-Type', ''):
                return response
        except Exception as e:
            print("tts error:",e,"retrying...")
            retry+=1
    raise TimeoutError

async def play_tts(response,text):
    # 创建自定义临时目录
    temp_dir = os.path.join(os.getcwd(), "tts_temp")
    os.makedirs(temp_dir, exist_ok=True)

    # 生成唯一文件名
    timestamp = int(time.time() * 1000)
    temp_file = os.path.join(temp_dir, f"tts_{timestamp}.wav")

    # 写入文件
    with open(temp_file, "wb") as f:
        f.write(response.content)
    audio = AudioSegment.from_wav(temp_file)
    if config['beta_config']['beta_open_vts_emotion']:
        await vts_emotion.emotion_main()
    output_string(text)
    winsound.PlaySound(temp_file, winsound.SND_FILENAME)
    try:
        os.remove(temp_file)
    except Exception as e:
        print(f"删除临时文件失败: {e}")
    if config['beta_config']['beta_open_vts_emotion']:
        await vts_emotion.emotion_main()
    return

#用于一定长度文字换行的函数
def output_string(text) :
    with open("logs\\output.txt","a+",encoding='utf-8') as f:
        print(text,file=f)
    return

#更改AI状态
def mode_change(mode) :
    with open("logs\\mode.txt","w",encoding='utf-8') as f:
        print("mode:"+mode,file=f)
    return


#重置上下文
def removecontext():
    global message
    #print(config['llm_config']['llm_prompt'])
    message=copy.deepcopy(config['llm_config']['llm_prompt'])
    #print(message)
    with open("logs\\text.json","w",encoding='utf-8') as f:
        json.dump(message,f,ensure_ascii=False,indent=4)
    return

def write_text(text) :
    with open("logs\\text.json","w",encoding='utf-8') as f:
        json.dump(text,f,ensure_ascii=False,indent=4)
    return

def add_message_in_request(message,added,username) :
    message += f"\n{username}: {added}"
    return message

def add_gift_in_message(gifts):
    giftstr='\n[直播间消息]'
    for gift in gifts:
        if gift['type'] == 'like' :
            giftstr += ' '+gift['user']+'给直播间点了'+str(gift['message'])+'个赞 '
        if gift['type'] == 'gift' :
            giftstr += ' '+gift['user']+'送了礼物：'+gift['message']+' '
    giftstr += '[直播间消息结束]'
    return giftstr

async def main():
    global message
    print("listening...")
    removecontext()
    write_text(message)

    waiting_requests=deque()
    now_messages_added = 0
    current_task = None

    gift_send = deque()

    listnow=0
    sing_last_time=0
    mode_change("chat（读取弹幕）")
    async with aiohttp.ClientSession() as session:
        while True :
            #print(current_task)
            #if current_task is not None:
                #print(current_task.done())
            if current_task is not None and current_task.done() :
                try:
                    ans=current_task.result()
                    tokens_used = ans['usage']['total_tokens']
                    print("tokens used:" + str(tokens_used))
                    ans = ans['choices'][0]['message']
                    ansstr = ans['content']
                    message.append(ans)
                    write_text(message)
                    ansstr = ansstr[len(config['llm_config']['llm_rolename']) + 1:] if ansstr.startswith(
                            config['llm_config']['llm_rolename']) else ansstr
                    print(ansstr)
                    if len(waiting_requests) :
                        message.append( waiting_requests[0]['request_content'] )
                        now_messages_added = waiting_requests[0]['now_added']
                        waiting_requests.popleft()
                        current_task = create_task(request_firefly(session,message),name = "streaming-firefly")
                        if len(gift_send):

                            message[-1]['content'][0]['text'] += add_gift_in_message(gift_send)

                        print("从缓冲队列中提取堆积消息处理")
                    else :
                        current_task =None
                        now_messages_added = 0
                    gift_send.clear()
                    res=await TTS(ansstr)
                    await play_tts(res,ansstr)

                    if tokens_used>config['llm_config']["llm_maxitoken"]:
                        removecontext()
                except asyncio.CancelledError:
                    print("返回任务结果时出现问题：任务异常取消")
                    current_task = None
                    now_messages_added = 0
                except Exception as e:
                    print("返回任务结果时出现其他问题：",e)
            #读取命令
            try:
                with open("logs\\command.json",'r',encoding='utf-8') as f:
                    slist=json.load(f)
            except Exception as e:
                print(e)
                continue
            try:
                with open("logs\\text.json",'r',encoding='utf-8') as f:
                    message=json.load(f)
            except Exception as e:
                print(e)
                continue
            #'''
            #转换模式（翻唱结束）
            if sing_last_time==1:
                mode_change("chat（读取弹幕）")
                listnow=len(slist)-1
                sing_last_time=0
            if slist[listnow].get("type",'0')=='0' :
                await asyncio.sleep(1)
                continue

            elif slist[listnow].get('type','0')=='rem':
                removecontext()
                print("removed!")
            #唱歌
            elif slist[listnow].get('type','0')=='aising':
                mode_change("singing（忽略弹幕消息）")
                if config['beta_config']['beta_open_sing_control']:
                    set_process_volume(config['beta_config']['beta_sing_control'],0)
                winsound.PlaySound("AI\\"+str(slist[listnow]['messages'])+".WAV", winsound.SND_FILENAME)
                if config['beta_config']['beta_open_sing_control']:
                    set_process_volume(config['beta_config']['beta_sing_control'],1)
                sing_last_time=1

            #这里是直播间礼物的处理序列逻辑，但是未实现直播间消息合并至请求，这是你明天要做的别忘了
            elif slist[listnow].get('type','0') == "gift" :
                gift_send.append({"user":slist[listnow]['user'],"type":"gift","message":slist[listnow]['messages']})

                while len(gift_send) > config['live_config']['live_maxi_live_message']:
                    gift_send.popleft()

            elif slist[listnow].get('type','0') == "like" :
                flag = 0
                for i in gift_send:
                    if i['user']==slist[listnow]['user'] and i['type']=='like' :
                        i['message'] += slist[listnow]['messages']
                        flag = 1
                        break
                if flag == 0 :
                    gift_send.append({"user":slist[listnow]['user'],"type":"like","message":slist[listnow]['messages']})

                while len(gift_send) > config['live_config']['live_maxi_live_message']:
                    gift_send.popleft()

            #弹幕聊天
            elif slist[listnow].get("type",'0')=='DM':


                #延迟判定
                if time.time()-slist[listnow].get("time",0) >= config['llm_config']['llm_maxidelay'] :
                    print("timeout!")
                    pass
                else:
                    #不需要try except是因为我们在这里已经确定了任务没有结束
                    if now_messages_added < config['llm_config']['llm_maximerge'] and now_messages_added != 0 and len(waiting_requests) == 0 :
                        if current_task is not None and current_task.done() == False :
                            try:
                                current_task.cancel()
                                await current_task
                            except asyncio.CancelledError :
                                print("尝试重发消息出现异常：任务已取消")
                            print(message[-1])
                            if message[-1]['content'][0]['text'].find(r'\n[直播间消息]') != -1:
                                message[-1]['content'][0]['text']=message[-1]['content'][0]['text'][ : message[-1]['content'][0]['text'].find(r'\n直播间消息') ]
                            message[-1]['content'][0]['text'] = add_message_in_request( message[-1]['content'][0]['text'] , slist[listnow]['messages'], slist[listnow]['user'])
                            if len(gift_send) :

                                message[-1]['content'][0]['text'] += add_gift_in_message(gift_send)

                            write_text(message)
                            current_task = create_task(request_firefly(session,message),name = "streaming-firefly")
                            now_messages_added += 1
                            print("取消请求，添加新的请求，当前合并弹幕数量",now_messages_added)
                        listnow += 1
                        continue

                    elif now_messages_added == 0 and len(waiting_requests) == 0 and current_task is None :
                        message.append({"role":"user","content":[{"type":"text","text":slist[listnow].get("user","匿名")+': '+slist[listnow].get("messages",'你好流萤')}]})
                        if len(gift_send):
                            message[-1]['content'][0]['text'] += add_gift_in_message(gift_send)
                        write_text(message)
                        now_messages_added  = 1
                        current_task = create_task(request_firefly(session,message),name = "streaming-firefly")
                        print("发送新的request，当前列表空闲")

                    else :
                        if len(waiting_requests) == 0 or waiting_requests[-1]['now_added'] == config['llm_config']['llm_maximerge'] :
                            waiting_requests.append({"now_added": 1 , "request_content":{"role": "user", "content": [{"type": "text",
                                                                         "text": slist[listnow].get("user", "匿名") + ':' +
                                                                                 slist[listnow].get("messages",
                                                                                                    '你好流萤')}]}})
                        else :
                            waiting_requests[-1]['request_content']['content'][0]['text'] = add_message_in_request( waiting_requests[-1]['request_content'][0]['text'] , slist[listnow]['messages'], slist[listnow]['user'] )
                            waiting_requests[-1]['now_added'] += 1
                        print("弹幕堆积中，已添加至缓冲队列")

            listnow+=1
    return

if __name__ == '__main__':
    asyncio.run(main())