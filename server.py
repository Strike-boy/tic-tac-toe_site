# server.py
import time, secrets, string, asyncio, json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

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
    code = gen_code()
    games[code] = {
        "sockets": [],
        "players": [],
        "board": ['']*9,
        "turn": "X",
        "state": "waiting",
        "created": time.time(),
        "messages": []
    }
    return {"code": code}

async def send_safe(ws, payload):
    try:
        await ws.send_text(json.dumps(payload))
    except:
        pass

async def broadcast_room(room, payload):
    for ws in room["sockets"]:
        await send_safe(ws, payload)

@app.websocket("/ws/{code}")
async def ws_endpoint(websocket: WebSocket, code: str):
    await websocket.accept()
    name = websocket.query_params.get('name', 'Игрок')
    room = games.get(code)
    
    if not room:
        await send_safe(websocket, {"type":"error","msg":"Комната не найдена"})
        await websocket.close()
        return
    
    if len(room["sockets"]) >= 2:
        await send_safe(websocket, {"type":"error","msg":"Комната заполнена"})
        await websocket.close()
        return

    symbol = 'X' if len(room["sockets"]) == 0 else 'O'
    room["sockets"].append(websocket)
    room["players"].append({"name": name, "symbol": symbol})

    if len(room["sockets"]) == 1:
        await send_safe(websocket, {
            "type": "waiting",
            "your_symbol": symbol,
            "board": room["board"],
            "turn": room["turn"]
        })
    else:
        room["state"] = "playing"
        p0, p1 = room["players"][0], room["players"][1]
        
        await send_safe(room["sockets"][0], {
            "type":"ready",
            "your_symbol": p0["symbol"],
            "opponent": p1["name"],
            "board": room["board"],
            "turn": room["turn"]
        })
        await send_safe(room["sockets"][1], {
            "type":"ready",
            "your_symbol": p1["symbol"],
            "opponent": p0["name"],
            "board": room["board"],
            "turn": room["turn"]
        })

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message["type"] == "move":
                idx = message["index"]
                player_idx = room["sockets"].index(websocket)
                player_symbol = room["players"][player_idx]["symbol"]
                
                if (room["turn"] == player_symbol and 
                    room["state"] == "playing" and 
                    room["board"][idx] == ''):
                    
                    room["board"][idx] = player_symbol
                    winner = check_win(room["board"])
                    
                    if winner:
                        room["state"] = "finished"
                        await broadcast_room(room, {
                            "type": "state",
                            "board": room["board"],
                            "turn": room["turn"],
                            "winner": winner
                        })
                    else:
                        room["turn"] = "O" if room["turn"] == "X" else "X"
                        await broadcast_room(room, {
                            "type": "state",
                            "board": room["board"],
                            "turn": room["turn"],
                            "winner": None
                        })
            
            elif message["type"] == "chat":
                player_idx = room["sockets"].index(websocket)
                player_name = room["players"][player_idx]["name"]
                await broadcast_room(room, {
                    "type": "chat",
                    "sender": player_name,
                    "message": message["message"]
                })
            
            elif message["type"] == "rematch" and room["state"] == "finished":
                room["board"] = ['']*9
                room["turn"] = "X"
                room["state"] = "playing"
                await broadcast_room(room, {
                    "type": "state",
                    "board": room["board"],
                    "turn": room["turn"],
                    "winner": None
                })
                
    except WebSocketDisconnect:
        room["sockets"].remove(websocket)
        room["players"] = [p for p in room["players"] if p["name"] != name]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
