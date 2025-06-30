import subprocess
from openai import OpenAI
import json
from time import sleep
import reading_config
import threading
from multiprocessing.managers import BaseManager

config=reading_config.read_config()

sing_list=config['live_config']['live_sing_list']
dmcount=[]

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

if __name__ == '__main__':

    process_llm=subprocess.Popen(['python',"main_process.py"])
    process_ws=subprocess.Popen(['python',"ws.py"])


    listnow=0
    processlist=0
    todo_list=[]
    todo_list.append({"type":'0',"messages":'0',"user":"null"})
    prompt = '\n'.join(config['filter_config']['filter_prompt'])
    message=[{"role":"system","content":prompt},{}]
    with open("logs\\command.json",'w',encoding='utf-8') as f:
        json.dump(todo_list,f,ensure_ascii=False,indent=4)
    with open("logs\\todo_raw.json","w",encoding='utf-8') as f:
        json.dump([],f,ensure_ascii=False,indent=4)
    while True:
        if process_ws.poll() is not None:

            print("ws停止，code：",process_ws.returncode,"restarting...")
            process_ws=subprocess.Popen(['python',"ws.py"])

        if process_llm.poll() is not None:

            print("process停止，code",process_llm.returncode,"restarting...")
            process_llm=subprocess.Popen(['python',"main_process.py"])
        #'''
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

        elif raw_list[processlist].get("cmd",'null')=='LIVE_OPEN_PLATFORM_DM':
            if raw_list[processlist].get('message','')=='remtext' and (raw_list[processlist].get('admin',0)==1 or raw_list[processlist].get("username",'unknown')==config['live_config']['live_upid']):
                add_list('rem','','',0)
            elif raw_list[processlist].get('message','')[0:3]=='点歌 ':
                pass
            elif raw_list[processlist].get('message','')[0:3]=='翻唱 ':
                flag=0
                for user in dmcount:
                    if user['user'] == raw_list[processlist]['username'] and user['count'] >= config['live_config']['live_sing_count'] :
                        user['count'] -= 5
                        flag = 1
                        break
                #'''
                if flag==0 :
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
            elif raw_list[processlist].get('message','')[0]=='#' :
                pass
            else:
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
                if resp.choices[0].message.content=='process':
                    flag=0
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

