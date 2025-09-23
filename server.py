# server.py
import time, secrets, string, asyncio, json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List, Set

app = FastAPI()
# Для разработки разрешаем всё (на проде ограничь домены)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# games: code -> { 
#   sockets: [websocket,...], 
#   players: [{'name':..,'symbol':..}], 
#   board:[...], 
#   turn:'X'/'O', 
#   state:'waiting'/'playing'/'finished',
#   created:ts,
#   rematch_votes: set(),
#   messages: List[dict]  # Новое: история чата
# }
games: Dict[str, dict] = {}

def gen_code(length=4):
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(secrets.choice(alphabet) for _ in range(length))
        if code not in games:
            return code

def check_win(board):
    wins = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
    for a,b,c in wins:
        if board[a] and board[a]==board[b]==board[c]:
            return board[a], [a, b, c]  # Возвращаем победителя и комбинацию
    if '' not in board:
        return 'D', []  # Ничья
    return None, []  # Игра продолжается

@app.post("/create")
async def create_room(req: Request):
    data = {}
    try:
        data = await req.json()
    except:
        data = {}
    code = gen_code()
    games[code] = {
        "sockets": [],
        "players": [],
        "board": ['']*9,
        "turn": "X",
        "state": "waiting",
        "created": time.time(),
        "rematch_votes": set(),
        "messages": []  # История сообщений чата
    }
    return {"code": code}

@app.get("/status/{code}")
async def status(code: str):
    room = games.get(code)
    if not room:
        raise HTTPException(status_code=404, detail="Not found")
    return {
        "players": len(room["players"]), 
        "state": room["state"],
        "player_names": [player["name"] for player in room["players"]]
    }

@app.get("/room/{code}/messages")
async def get_messages(code: str):
    room = games.get(code)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return {"messages": room["messages"][-50:]}  # Последние 50 сообщений

async def send_safe(ws, payload):
    try:
        await ws.send_text(json.dumps(payload))
    except:
        pass

async def broadcast_room(room, payload, exclude_ws=None):
    dead = []
    for ws in list(room["sockets"]):
        if ws == exclude_ws:
            continue
        try:
            await ws.send_text(json.dumps(payload))
        except:
            dead.append(ws)
    for d in dead:
        if d in room["sockets"]:
            idx = room["sockets"].index(d)
            room["sockets"].pop(idx)
            room["players"].pop(idx)

@app.websocket("/ws/{code}")
async def ws_endpoint(websocket: WebSocket, code: str):
    await websocket.accept()
    params = websocket.query_params
    name = params.get('name', 'Игрок')
    room = games.get(code)
    
    if not room:
        await send_safe(websocket, {"type":"error","msg":"Комната не найдена"})
        await websocket.close()
        return
    
    if len(room["sockets"]) >= 2:
        await send_safe(websocket, {"type":"error","msg":"Комната заполнена"})
        await websocket.close()
        return

    # assign symbol based on join order
    symbol = 'X' if len(room["sockets"]) == 0 else 'O'
    
    # add to room
    room["sockets"].append(websocket)
    room["players"].append({"name": name, "symbol": symbol})
    
    # Отправляем историю чата новому игроку
    if room["messages"]:
        await send_safe(websocket, {
            "type": "chat_history",
            "messages": room["messages"][-20:]  # Последние 20 сообщений
        })
    
    # send waiting/ready
    if len(room["sockets"]) == 1:
        await send_safe(websocket, {
            "type": "waiting",
            "your_symbol": symbol,
            "board": room["board"],
            "turn": room["turn"],
            "opponent": None
        })
    else:
        # both connected -> notify both with assignment
        p0 = room["players"][0]
        p1 = room["players"][1]
        room["state"] = "playing"
        
        # inform player 0
        await send_safe(room["sockets"][0], {
            "type":"ready",
            "your_symbol": p0["symbol"],
            "opponent": p1["name"],
            "board": room["board"],
            "turn": room["turn"]
        })
        # inform player 1
        await send_safe(room["sockets"][1], {
            "type":"ready",
            "your_symbol": p1["symbol"],
            "opponent": p0["name"],
            "board": room["board"],
            "turn": room["turn"]
        })
        
        # Уведомляем о подключении второго игрока
        await broadcast_room(room, {
            "type": "player_joined",
            "player_name": name,
            "message": f"{name} присоединился к игре!"
        })

    try:
        while True:
            text = await websocket.receive_text()
            try:
                data = json.loads(text)
            except:
                continue
                
            typ = data.get('type')

            if typ == 'move':
                idx = int(data.get('index', -1))
                if idx < 0 or idx > 8:
                    await send_safe(websocket, {"type":"error","msg":"Неверный индекс"})
                    continue
                
                # кто ходит
                if websocket not in room["sockets"]:
                    continue
                    
                sender_idx = room["sockets"].index(websocket)
                sender_symbol = room["players"][sender_idx]["symbol"]
                sender_name = room["players"][sender_idx]["name"]
                
                # проверка очереди
                if room["turn"] != sender_symbol:
                    await send_safe(websocket, {"type":"error","msg":"Не ваш ход"})
                    continue
                    
                if room["board"][idx] != '':
                    await send_safe(websocket, {"type":"error","msg":"Клетка занята"})
                    continue
                    
                # применяем ход
                room["board"][idx] = sender_symbol
                
                # проверка конца игры
                winner, win_combo = check_win(room["board"])
                
                if winner == 'D':
                    room["state"] = "finished"
                    await broadcast_room(room, {
                        "type":"state",
                        "board": room["board"],
                        "turn": room["turn"],
                        "winner": "D",
                        "win_combo": win_combo,
                        "message": "Ничья!"
                    })
                elif winner in ('X','O'):
                    room["state"] = "finished"
                    winner_name = next((p["name"] for p in room["players"] if p["symbol"] == winner), winner)
                    await broadcast_room(room, {
                        "type":"state",
                        "board": room["board"],
                        "turn": room["turn"],
                        "winner": winner,
                        "win_combo": win_combo,
                        "winner_name": winner_name,
                        "message": f"{winner_name} победил!"
                    })
                else:
                    room["turn"] = 'O' if room["turn"] == 'X' else 'X'
                    await broadcast_room(room, {
                        "type":"state",
                        "board": room["board"],
                        "turn": room["turn"],
                        "winner": None,
                        "message": f"Ход переходит к {room['turn']}"
                    })

            elif typ == "rematch":
                # Разрешаем реванш если игра завершена ИЛИ если противник вышел
                if room["state"] not in ["finished", "playing"]:
                    await send_safe(websocket, {"type":"error","msg":"Игра ещё не закончена"})
                    continue

                # Сбрасываем голоса если это первый голос
                if "rematch_votes" not in room:
                    room["rematch_votes"] = set()
                
                room["rematch_votes"].add(websocket)

                # Уведомляем о голосе
                sender_idx = room["sockets"].index(websocket)
                sender_name = room["players"][sender_idx]["name"]
                await broadcast_room(room, {
                    "type": "rematch_vote",
                    "player_name": sender_name,
                    "votes": len(room["rematch_votes"]),
                    "total_players": len(room["sockets"])
                })

                # Если все игроки согласны
                if len(room["rematch_votes"]) == len(room["sockets"]):
                    # Полный сброс игры
                    room["board"] = ['']*9
                    room["turn"] = "X"
                    room["state"] = "playing"
                    room["rematch_votes"] = set()

                    # Уведомляем всех
                    await broadcast_room(room, {
                        "type": "rematch_start",
                        "board": room["board"],
                        "turn": room["turn"],
                        "message": "Реванш начинается!"
                    })

            elif typ == "chat":
                # Обработка чата
                message = data.get('message', '').strip()
                if message:
                    sender_idx = room["sockets"].index(websocket)
                    sender_name = room["players"][sender_idx]["name"]
                    
                    chat_message = {
                        "sender": sender_name,
                        "message": message,
                        "timestamp": time.time()
                    }
                    
                    # Сохраняем в историю
                    room["messages"].append(chat_message)
                    
                    # Отправляем всем
                    await broadcast_room(room, {
                        "type": "chat",
                        "sender": sender_name,
                        "message": message,
                        "timestamp": chat_message["timestamp"]
                    })
                    
            elif typ == "emoji":
                # Обработка эмодзи-реакций
                emoji = data.get('emoji', '')
                if emoji:
                    sender_idx = room["sockets"].index(websocket)
                    sender_name = room["players"][sender_idx]["name"]
                    
                    await broadcast_room(room, {
                        "type": "emoji",
                        "sender": sender_name,
                        "emoji": emoji,
                        "timestamp": time.time()
                    }, exclude_ws=websocket)

    except WebSocketDisconnect:
        if websocket in room["sockets"]:
            idx = room["sockets"].index(websocket)
            room["sockets"].pop(idx)
            left_player = room["players"].pop(idx)
            
            # Очищаем голоса за реванш
            if "rematch_votes" in room:
                room["rematch_votes"] = {ws for ws in room["rematch_votes"] if ws != websocket}
            
            if room["sockets"]:
                await send_safe(room["sockets"][0], {
                    "type":"opponent_left",
                    "msg":f"{left_player['name']} покинул игру",
                    "player_name": left_player["name"]
                })
                
                # Если игра была в процессе, заканчиваем её
                if room["state"] == "playing":
                    room["state"] = "finished"
                    await send_safe(room["sockets"][0], {
                        "type":"game_ended",
                        "reason": "opponent_left",
                        "message": "Противник покинул игру. Вы победили!"
                    })
            
            # Если комната пустая, удаляем её через некоторое время
            if not room["sockets"]:
                await asyncio.sleep(300)  # 5 минут
                if code in games and not games[code]["sockets"]:
                    del games[code]

# Новый endpoint для очистки старых комнат
@app.post("/cleanup")
async def cleanup_rooms():
    current_time = time.time()
    rooms_to_delete = []
    
    for code, room in games.items():
        # Удаляем комнаты без игроков старше 1 часа
        if not room["sockets"] and current_time - room["created"] > 3600:
            rooms_to_delete.append(code)
    
    for code in rooms_to_delete:
        del games[code]
    
    return {"deleted_rooms": len(rooms_to_delete), "active_rooms": len(games)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
