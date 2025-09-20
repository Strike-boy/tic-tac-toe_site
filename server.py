# server.py
import time, secrets, string, asyncio, json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
# Для разработки разрешаем всё (на проде ограничь домены)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# games: code -> { sockets: [websocket,...], players: [{'name':..,'symbol':..}], board:[...], turn:'X'/'O', state:'waiting'/'playing', created:ts }
games = {}

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
            return board[a]
    if '' not in board:
        return 'D'
    return None

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
        "created": time.time()
    }
    return {"code": code}

@app.get("/status/{code}")
async def status(code: str):
    room = games.get(code)
    if not room:
        raise HTTPException(status_code=404, detail="Not found")
    return {"players": len(room["players"]), "state": room["state"]}

async def send_safe(ws, payload):
    try:
        await ws.send_text(json.dumps(payload))
    except:
        pass

async def broadcast_room(room, payload):
    dead = []
    for ws in list(room["sockets"]):
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
    # send waiting/ready
    if len(room["sockets"]) == 1:
        await send_safe(websocket, {"type":"waiting","your_symbol": symbol, "board": room["board"], "turn": room["turn"], "opponent": None})
    else:
        # both connected -> notify both with assignment
        p0 = room["players"][0]
        p1 = room["players"][1]
        room["state"] = "playing"
        # inform player 0
        await send_safe(room["sockets"][0], {"type":"ready","your_symbol": p0["symbol"], "opponent": p1["name"], "board": room["board"], "turn": room["turn"]})
        # inform player 1
        await send_safe(room["sockets"][1], {"type":"ready","your_symbol": p1["symbol"], "opponent": p0["name"], "board": room["board"], "turn": room["turn"]})

    try:
        while True:
            text = await websocket.receive_text()
            try:
                data = json.loads(text)
            except:
                continue
            typ = data.get('type')
            if typ == 'join':
                # already handled by websocket query param; nothing extra
                continue
            if typ == 'move':
                idx = int(data.get('index', -1))
                if idx < 0 or idx > 8:
                    await send_safe(websocket, {"type":"error","msg":"Неверный индекс"})
                    continue
                # who is sender?
                if websocket not in room["sockets"]:
                    continue
                sender_idx = room["sockets"].index(websocket)
                sender_symbol = room["players"][sender_idx]["symbol"]
                # check turn
                if room["turn"] != sender_symbol:
                    await send_safe(websocket, {"type":"error","msg":"Не ваш ход"})
                    continue
                if room["board"][idx] != '':
                    await send_safe(websocket, {"type":"error","msg":"Клетка занята"})
                    continue
                # apply move
                room["board"][idx] = sender_symbol
                # check win/draw
                w = check_win(room["board"])
                if w == 'D':
                    room["state"] = "finished"
                    await broadcast_room(room, {"type":"state","board":room["board"], "turn": room["turn"], "winner":"D"})
                elif w in ('X','O'):
                    room["state"] = "finished"
                    await broadcast_room(room, {"type":"state","board":room["board"], "turn": room["turn"], "winner": w})
                else:
                    # switch turn
                    room["turn"] = 'O' if room["turn"] == 'X' else 'X'
                    await broadcast_room(room, {"type":"state","board":room["board"], "turn": room["turn"], "winner": None})
            # ignore other types
    except WebSocketDisconnect:
        # remove socket and notify other
        if websocket in room["sockets"]:
            idx = room["sockets"].index(websocket)
            room["sockets"].pop(idx)
            left_player = room["players"].pop(idx)
            # notify remaining
            if room["sockets"]:
                await send_safe(room["sockets"][0], {"type":"opponent_left","msg":f"{left_player['name']} покинул игру"})
        # optionally cleanup empty rooms after some time
    except Exception as e:
        print("WS error:", e)
        # ensure cleanup
        if websocket in room["sockets"]:
            idx = room["sockets"].index(websocket)
            room["sockets"].pop(idx)
            room["players"].pop(idx)
