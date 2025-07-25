import subprocess
import time
from openai import OpenAI
import json
from time import sleep
import reading_config

config=reading_config.read_config()

sing_list=config['live_config']['live_sing_list']
dmcount=[]
#过滤器访问
def requestds(question):
    retry=0
    while retry<= config['filter_config']['filter_maxitry'] :
        try :
            client = OpenAI(api_key=config['filter_config']['filter_key'], base_url=config['filter_config']['filter_baseurl'])
            response = client.chat.completions.create(
                timeout=config['filter_config']['filter_timeout'],
                model=config['filter_config']['filter_model'],
                messages=question,
                stream=False
            )
            return response
        except Exception as e :
            print("filter error as ",e," retrying...")
            retry+=1
        finally :
            if 'client' :
                client.close() 
    raise TimeoutError
#command列表添加
def add_list(command_type, msg, command_user, time):
    global processlist,raw_list,listnow,todo_list
    todo_list[listnow]['type']=command_type
    todo_list[listnow]["messages"]=msg
    todo_list[listnow]['user']=command_user
    todo_list[listnow]['time']=time#注意！添加消息在这里！
    todo_list.append({"type":'0',"messages":'0',"user":'null',"time":0})
    with open("logs\\command.json",'w',encoding='utf-8') as f:
        json.dump(todo_list,f,ensure_ascii=False,indent=4)
    listnow+=1
    return

def legal_game_command(text):
    if not 'A'<=text[0]<='J':
        return False
    if len(text) >=4 or len(text) <=1:
        return False
    if len(text) ==2 :
        if '1'<=text[1]<='9':
            return True
        else :
            return False
    if len(text) ==3:
        if text[1:3]=='10':
            return True
        else :
            return False
    return False


if __name__ == '__main__':
    #同步启动子进程
    process_llm=subprocess.Popen(['python',"main_process.py"])
    process_ws=subprocess.Popen(['python',"ws.py"])


    listnow=0
    processlist=0
    todo_list=[]
    game_list=[]

    nowgame=0
    game_user=''
    game_command_last_time=0
    todo_list.append({"type":'0',"messages":'0',"user":"null"})
    prompt = '\n'.join(config['filter_config']['filter_prompt'])
    message=[{"role":"system","content":prompt},{}]
    with open("logs\\command.json",'w',encoding='utf-8') as f:
        json.dump(todo_list,f,ensure_ascii=False,indent=4)
    with open("logs\\todo_raw.json","w",encoding='utf-8') as f:
        json.dump([],f,ensure_ascii=False,indent=4)
    while True:
        #子进程异常关闭监测
        if process_ws.poll() is not None:

            print("ws停止，code：",process_ws.returncode,"restarting...")
            process_ws=subprocess.Popen(['python',"ws.py"])

        if process_llm.poll() is not None:

            print("process停止，code",process_llm.returncode,"restarting...")
            process_llm=subprocess.Popen(['python',"main_process.py"])
        #'''
        try:
            if process_game.poll() is not None:
                print("game停止，游戏重置")
                nowgame=False
        except Exception :
            pass
        try:
            with open("logs\\todo_raw.json","r",encoding='utf-8') as f:
                raw_list=json.load(f)
        except Exception as e :
            print("fail to read the raw!")
            sleep(1)
        #'''
        if len(raw_list)<=processlist:
            #print(len(raw_list))
            sleep(1)
            continue
        #超时结束游戏
        if nowgame :
            if time.time()-game_command_last_time>config['beta_config']['beta_gamemode_timeout']:
                nowgame=0
                try:
                    process_game.kill()
                    print("game killed!")
                except Exception as e :
                    print("fail to kill the game!")
        #输入游戏命令
        if nowgame and raw_list[processlist].get('username')==game_user and legal_game_command(raw_list[processlist].get('message')):
            print('game message get!')
            text=raw_list[processlist].get('message')
            game_dict={"cmd":"down","message":(ord(text[0])-ord('A')+1,int(text[1:]))}
            game_list.append(game_dict)
            with open("logs\\game.json","w",encoding='utf-8') as f:
                json.dump(game_list,f,ensure_ascii=False,indent=4)
            game_command_last_time=time.time()
        #简单命令的处理（进入直播间，送礼，点赞，大航海）
        elif raw_list[processlist].get('cmd','null')=="LIVE_OPEN_PLATFORM_LIVE_ROOM_ENTER" :
            with open("logs\\livetext.txt",'a+',encoding='utf-8') as f:
                print("欢迎 "+raw_list[processlist]['username']+" 喵",file=f)

        elif raw_list[processlist].get('cmd','null')=='LIVE_OPEN_PLATFORM_SEND_GIFT':
            with open("logs\\livetext.txt",'a+',encoding='utf-8') as f:
                print("感谢 "+raw_list[processlist]['username']+" 投喂的"+raw_list[processlist]['message']+"谢谢喵",file=f)

        elif raw_list[processlist].get('cmd','null')=='LIVE_OPEN_PLATFORM_LIKE':
            with open("logs\\livetext.txt",'a+',encoding='utf-8') as f:
                print("感谢 "+raw_list[processlist]['username']+" 的 " + str(raw_list[processlist]['message']) +" 个喜欢喵",file=f)

        elif raw_list[processlist].get('cmd' , 'null' ) == 'LIVE_OPEN_PLATFORM_GUARD' :
            lv=raw_list[processlist].get( 'message' , -1 )
            if lv==1 :
                gtype='总督'
            elif lv==2 :
                gtype='提督'
            else :
                gtype='舰长'
            with open('logs\\livetext.txt','a+',encoding='utf-8') as f:
                print("谢谢 "+raw_list[processlist]['username'] + '的'+gtype+"\n谢谢老板老板大气喵")
        #弹幕处理
        elif raw_list[processlist].get("cmd",'null')=='LIVE_OPEN_PLATFORM_DM':
            #移除上下文，判定是否为房管或主播鉴权
            if raw_list[processlist].get('message','')=='remtext' and (raw_list[processlist].get('admin',0)==1 or raw_list[processlist].get("username",'unknown')==config['live_config']['live_upid']):
                add_list('rem','','',0)
            #开了点歌机，这里直接不做处理
            elif raw_list[processlist].get('message','')[0:3]=='点歌 ':
                pass
            #翻唱命令的添加
            elif raw_list[processlist].get('message','')[0:3]=='翻唱 ':
                flag=0
                #检查是否有翻唱命令权限
                for user in dmcount:
                    if user['user'] == raw_list[processlist]['username'] and user['count'] >= config['live_config']['live_sing_count'] :
                        user['count'] -= config['live_config']['live_sing_count']
                        flag = 1
                        break
                #'''
                if flag==0 and config['live_config']['live_sing_count']:
                    processlist += 1
                    continue
                #'''
                singname=raw_list[processlist]['message'][3:len(raw_list[processlist]['message'])]
                print("点歌要求符合")
                for sings in sing_list:
                    if singname==str(sings['num']) or singname==str(sings['name']):
                        add_list('aising',sings['name'],'',0)
                        print("ai list added!")
                        break
            #跳过命令
            elif raw_list[processlist].get('message','')[0]=='#' :
                pass
            #游戏代码集成
            elif raw_list[processlist].get('message','') == "game" and config['beta_config']['beta_open_gamemode']:
                #我不知道为什么鉴权要写这么长
                if nowgame == 1 :
                    processlist += 1
                    continue
                flag=0
                for user in dmcount:
                    if dmcount['user'] == raw_list[processlist]['username'] :
                        if dmcount['count'] >= config['beta_config']['beta_gamemode_danmaku'] :
                            dmcount["count"] -= config['beta_config']['beta_gamemode_danmaku']
                            flag = 1
                            break
                if flag==0 and config['beta_config']['beta_gamemode_danmaku'] :
                    processlist += 1
                    continue
                #开始游戏了
                nowgame= True
                game_user=raw_list[processlist]['username']
                game_command_last_time=time.time()
                game_list=[]
                add_dict={'cmd':'start','message':game_user}
                game_list.append(add_dict)
                print("game start:\nplayer:",game_user)
                with open("logs\\game.json", "w", encoding='utf-8') as f:
                    json.dump(game_list, f, ensure_ascii=False, indent=4)
                process_game=subprocess.Popen(['python',"game\\main.py"])

            #其他非命令弹幕
            else:
                #筛选弹幕
                while True:
                    try:
                        with open("logs\\text.json",'r',encoding='utf-8') as f:
                            mystr=f.read()
                        message[1]={"role":"user","content":mystr+"\nnew_danmaku："+raw_list[processlist].get("username","匿名")+":"+raw_list[processlist].get("message",'Hello?')}
                        break
                    except Exception as e:
                        sleep(1)
                        print("fail to read text")
                        pass
                print("OK,read the text")
                try :
                    resp=requestds(message)
                except TimeoutError :
                    print("Error:filter timed out,failed to process the danmaku.")
                    processlist+=1
                    continue
                #适合回答process
                if resp.choices[0].message.content=='process':
                    flag=0
                    #添加有效弹幕
                    for user in dmcount :
                        if user['user']==raw_list[processlist]['username']:
                            flag=1
                            user['count']+=1
                            break
                    if flag==0:
                        dmcount.append({"user":raw_list[processlist]['username'],"count":1})
                    print('OK,processing...')
                    add_list('DM',raw_list[processlist].get('message',''),raw_list[processlist].get('username',''),raw_list[processlist].get('time',0))
                else:
                    print("pass")
                    #print(resp.choices[0].message.reasoning_content)#reasoner
        processlist+=1