import random
import time
import numpy as np
import pygame
import math

pygame.init()

size = (800,600)

screen = pygame.display.set_mode(size)
pygame.display.set_caption("game test")

board=np.empty((11,11),dtype=object)
board_now=np.empty((11,11),dtype=object)
board_color=np.empty((11,11),dtype=object)
posx=0
posy=0
ex_move=1

def init_board():
    global board,board_now,board_color,posx,posy
    for i in range(1,11) :
        for j in range(1,11) :
            board[i,j]=pygame.Rect(20+i*50,20+j*50,40,40)
            board_now[i,j]=0
            board_color[i,j]=(173,216,230)
    board_now[5,5]=2
    board_color[5,5]=(220,20,60)
    posx=5
    posy=5
    done = 0
    random.seed(time.time())
    while done<3:
        i = random.randint(1,10)
        j = random.randint(1,10)
        if board_now[i,j] == 0:
            board_now[i,j]=1
            board_color[i,j]=(0,139,139)
            done+=1

    return

def downboard(pos) :
    global board,board_now,board_color
    for i in range(1,11) :
        for j in range(1,11) :
            if board[i,j].collidepoint(pos) and board_now[i,j] == 0:
                board_color[i,j]=(0,139,139)
                board_now[i,j]=1
                return True
    return False

def init_book():
    book=np.empty((11,11),dtype=object)
    for j in range(1, 11):
        for k in range(1, 11):
            book[j, k] = 0
    return book

def move_board():
    global nowmin,posx,posy,ex_move

    move_base = [(1,0),(0,1),(-1,0),(0,-1)]
    ex_move_base = [(1,1),(1,-1),(-1,1),(-1,-1)]

    for move in move_base :
        if move_legal(posx,posy,move) and move_win(posx,posy,move):
            return move

    if ex_move >0 :
        for move in ex_move_base :
            if move_legal(posx,posy,move) and move_win(posx,posy,move):
                ex_move-=1
                return move
    mini=-math.inf
    minimove=(0,0)
    for i,move in enumerate(move_base+ex_move_base) :
        if move_legal(posx,posy,move) :
            if i>3 and ex_move<=0 :
                continue

            nowmin = math.inf
            if i>3 :
                find_min_way(init_book(),posx+move[0],posy+move[1],ex_move-1,0)
            else :
                find_min_way(init_book(), posx + move[0], posy + move[1], ex_move , 0)
            grade_A=100 - 10*nowmin
            #if i>3 and ex_move==1 :
                #grade_A+=15
            if i>3 :#不知道为什么这里改成惩罚机制人机就比上面的会玩了，代码能跑就行了这种事你少管
                grade_A-=10
            grade_B=100 - scan_walls(posx+move[0],posy+move[1])
            if mini < grade_A*0.2+grade_B*0.8 :
                mini=grade_A*0.2+grade_B*0.8
                minimove=move
    #print(nowmin)
    if minimove[0]!=0 and minimove[1]!=0 :
        ex_move-=1
    return minimove

def scan_walls(posx,posy) :
    global board_now
    grade=0
    for i in range(1,11) :
        for j in range(1,11) :
            if board_now[i,j] == 1:
                way=abs(i-posx)+abs(j-posy)
                grade += 10-0.5*way
    return grade

def move_win(nowx,nowy,move) :
    if nowx+move[0] == 1 or nowx+move[0] == 10 or nowy+move[1]==1 or nowy+move[1] ==10 :
        return True
    else :
        return False

def move_legal(nowx,nowy,move) :
    global board_now
    if board_now[nowx+move[0],nowy+move[1]] == 0 and 1<= nowx+move[0] <= 10 and 1<= nowy+move[1] <= 10 :
        return True
    else :
        return False

nowmin=math.inf
def find_min_way(book,nowx,nowy,lastexmove,now):
    global board_now,nowmin
    move_base = [(1,0),(0,1),(-1,0),(0,-1)]
    ex_move_base = [(1,1),(1,-1),(-1,1),(-1,-1)]
    if now >= nowmin or book[nowx,nowy] == 1:
        return
    if nowx == 1 or nowy == 1 or nowx == 10 or nowy == 10 :
        nowmin=now
        return
    book[nowx,nowy]=1

    for move in move_base :
        if move_legal(nowx,nowy,move) :
            find_min_way(book,nowx+move[0],nowy+move[1],lastexmove, now+1)

    if lastexmove > 0 :
        for move in ex_move_base :
            if move_legal(nowx,nowy,move) :
                find_min_way(book,nowx+move[0],nowy+move[1],lastexmove-1, now+1)

    book[nowx,nowy]=0
    return

def process_move(move):
    global board_now,board_color,posx,posy
    board_now[posx,posy]=0
    board_color[posx,posy]=(173,216,230)
    posx+=move[0]
    posy+=move[1]
    board_now[posx,posy]=2
    board_color[posx,posy]=(220,20,60)

done = False
init_board()
finish= False
font = pygame.font.SysFont('microsoftyahei', 20)
textx=''
text_ex=font.render('斜向移动：有',True,(0,0,0))
image_player=pygame.image.load('player.png')
image_firefly=pygame.image.load('firefly.png')
while not done:
    move = 0
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            done = True
        if event.type == pygame.MOUSEBUTTONUP and finish == False:
            move=downboard(event.pos)

    if move :

        process_move(move_board())

        nowmin=math.inf
        find_min_way(init_book(), posx, posy, ex_move, 0)
        #print("min:",nowmin)
        if nowmin== math.inf:
            textx=font.render("<player>胜利",True,(0,0,0))
        elif nowmin==0:
            textx=font.render("流萤胜利",True,(0,0,0))
        if ex_move ==0 :
            text_ex=font.render("斜向移动：无",True,(0,0,0))

    screen.fill((255,255,255))

    if textx != '':
        #print('OK')
        screen.blit(textx,(80,20))
        finish = True
    if not finish:
        screen.blit(text_ex,(250,20))

    for i in range (1,11) :
        for j in range(1,11) :
            if board[i,j] is not None :
                pygame.draw.rect(screen,board_color[i,j],board[i,j],0)
                if board_now[i,j] == 1:
                    img_rect = image_player.get_rect(center=board[i, j].center)
                    screen.blit(image_player, img_rect)
                elif board_now[i,j] == 2:
                    img_rect = image_firefly.get_rect(center=board[i, j].center)
                    screen.blit(image_firefly, img_rect)

    pygame.display.flip()

pygame.quit()