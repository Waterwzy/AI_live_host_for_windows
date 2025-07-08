import pyautogui
import requests
import json
from openai import OpenAI
from pydub import AudioSegment
from pydub.playback import play
from io import BytesIO
import random
from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
import winsound
from psutil import NoSuchProcess, AccessDenied
import time
import win32gui
import win32con
import win32process
import psutil
import copy
import reading_config

config=reading_config.read_config()



def find_window_by_process_name(process_name):
    """通过进程名查找窗口句柄"""
    def callback(hwnd, hwnds):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if psutil.Process(pid).name() == process_name:
                hwnds.append(hwnd)
        return True
    
    hwnds = []
    win32gui.EnumWindows(callback, hwnds)
    return hwnds[0] if hwnds else None

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

'''qwen
def deepseekreq(question):
    # 启用流式输出（添加 stream=True）
    payload= {
        "model": "output",
        "messages": question,
        "max_tokens": 500,  # 限制响应的最大 token 数
        "sampler_override": {
            "frequency_penalty": 0.8,
            #"penalty": 400, 
            #"penalty_decay": 0.99654026,
            "presence_penalty": 0.3,
            "temperature": 1.4,
            #"top_k": 128,
            "top_p": 0.4,
            "type": "Nucleus"
        },
        "stream": False
    }
    response = requests.post(
        '我不到啊',
        json=payload,
        headers={"Authorization":f"Bearer 114","Content-Type": "application/json"},
    )
    return response
'''

#llm的访问过程，兼容openai接口
def request_firefly(question):
    retry=0
    while retry<=config['llm_config']['llm_maxitry'] :
        client = OpenAI(api_key=config['llm_config']['llm_key'], base_url=config['llm_config']['llm_baseurl'])
        try :
            response = client.chat.completions.create(
                model=config['llm_config']['llm_model'],
                messages=question,
                stream=False,
                timeout=config['llm_config']['llm_timeout'],
            )
            return response
        except Exception as e:
            print("Error in llm:",e," retrying...")
            retry+=1
        finally:
            if 'client' :
                client.close() 
    raise TimeoutError

#窗口置顶+快捷键，一堆bug的功能
def window_topmmost(processing_name) :
    # 1. 查找窗口
    hwnd = find_window_by_process_name(processing_name)
    if not hwnd:
        print(f"找不到进程 {processing_name} 的窗口")
        return

    # 2. 设置窗口置顶
    win32gui.SetWindowPos(
        hwnd, win32con.HWND_TOP,
        0, 0, 0, 0,
        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
    )

    
    # 3. 执行你的操作
    ran=random.randint(0,len( config['beta_config']['beta_vts_emotion_keys'] ) -1 )
    for i in range(len(config['beta_config']['beta_vts_emotion_keys'][ran])):
        pyautogui.keyDown(config['beta_config']['beta_vts_emotion_keys'][ran][i])
    for i in range(len(config['beta_config']['beta_vts_emotion_keys'][ran])):
        pyautogui.keyUp(config['beta_config']['beta_vts_emotion_keys'][ran][i])

    # 4. 直接回位到最底部
    win32gui.SetWindowPos(
        hwnd, win32con.HWND_BOTTOM,
        0, 0, 0, 0,
        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
    )

#tts文件，兼具输出音频流和文本功能，payload可以自己改
def TTS(text):
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
        "speed_factor": 0.85,
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
                    # 将二进制数据加载到内存中的 BytesIO 对象
                    audio_data = BytesIO(response.content)
                    # 用 pydub 解析并播放
                    audio = AudioSegment.from_wav(audio_data)
                    output_string(text)
                    if config['beta_config']['beta_open_vts_emotion']:
                        window_topmmost(config['beta_config']['beta_vts_emotion_process'])

                    play(audio)

                    if config['beta_config']['beta_open_vts_emotion']:
                        window_topmmost(config['beta_config']['beta_vts_emotion_process'])
                    return
        except Exception as e:
            print("tts error:",e,"retrying...")
            retry+=1
    raise TimeoutError


#用于一定长度文字换行的函数
def output_string(text) :
    maxi=config['live_config']['live_max_len']
    nowlen=0
    last_end=0
    with open("logs\\output.txt","a+",encoding='utf-8') as f:
        for i,c in enumerate(text) :
            if c == '\u3000' or '\u4e00' <= c <= '\u9fff' :
                nowlen+=2
            else :
                nowlen+=1
            if nowlen >= maxi :
                if nowlen == maxi :
                    print( text[last_end:i+1] ,file=f)
                    last_end=i+1
                    nowlen = 0
                else :
                    print( text[last_end : i ] ,file=f )
                    last_end = i
                    nowlen = 2
                #print("print!")
        print( text[last_end : len(text) ] ,file=f )
    return

#更改AI状态
def mode_change(mode) :
    with open("logs\\mode.txt","w",encoding='utf-8') as f:
        print("mode:"+mode,file=f)
    return

message = []
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

if __name__ == '__main__':
    
    print("listening...")
    removecontext()
    write_text(message)
    listnow=0
    sing_last_time=0
    mode_change("chat（读取弹幕）")
    while True :
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
        #弹幕聊天
        elif slist[listnow].get("type",'0')=='DM':
            #延迟判定
            if time.time()-slist[listnow].get("time",0) >= config['llm_config']['llm_maxidelay'] :
                print("timeout!")
                pass
            else:
                message.append({"role":"user","content":slist[listnow].get("user","匿名")+':'+slist[listnow].get("messages",'你好流萤')})
                #print("post request...")
                #print(message)
                try:
                    ans=request_firefly(message)#正常的request
                except TimeoutError:
                    print("Error:llm timed out,failed to process the command.")
                    if config['standby_llm_config']['standby_llm_open'] :
                        print("启动备用模型...")
                        mode_change("语言模型宕机，使用备用模型（无法语音转文字）")
                        client=OpenAI(api_key=config["standby_llm_config"]['standby_llm_key'],base_url=config["standby_llm_config"]['standby_llm_baseurl'])
                        standby_msg=copy.deepcopy(config['standby_llm_config']['standby_llm_prompt'])
                        for content in message :
                            standby_msg.append(content)
                        response=client.chat.completions.create(
                            model=config["standby_llm_config"]["standby_llm_model"],
                            messages=standby_msg,
                            stream=False
                        )
                        response=response.choices[0].message
                        response=response.model_dump()
                        response_add={"role":response['role'],"content":response['content']}
                        standby_msg.append(response_add)
                        output_string(response_add['content'])
                        print(response_add['content'])
                    listnow+=1
                    continue
                mode_change("chat（读取弹幕）")
                tokens_used=ans.usage.total_tokens
                print("tokens used:"+str(tokens_used))
                ans=ans.choices[0].message
                ans_dict=ans.model_dump()
                ans_add_dict={"role":ans_dict['role'],"content":ans_dict['content']}#简化字典结构
                ansstr=ans.content
                message.append(ans_add_dict)
                '''
                with open("logs\\historytext.txt","a+",encoding='utf-8') as f:
                    print("user:"+slist[listnow]['messages'],file=f)
                    print("assistant:"+ansstr,file=f)
                '''
                #print(message)
                '''#使用qwen
                ans=deepseekreq(message)
                ans=ans.json()
                message.append(ans["choices"][0]["message"])
                ansser=ans["choices"][0]["message"]["content"]
                '''
                print(ansstr)
                write_text(message)
                #ansstr=ansstr[3:len(ansstr)]
                try:
                    TTS(ansstr)
                except Exception as e:
                    print("failed to tts")
                if tokens_used>3000:
                    removecontext()
        listnow+=1