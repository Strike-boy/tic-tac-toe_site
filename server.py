import time
import secrets
import string
import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.game_rooms: Dict[str, dict] = {}

    async def connect(self, websocket: WebSocket, room_code: str):
        await websocket.accept()
        if room_code not in self.active_connections:
            self.active_connections[room_code] = []
        self.active_connections[room_code].append(websocket)

    def disconnect(self, websocket: WebSocket, room_code: str):
        if room_code in self.active_connections:
            self.active_connections[room_code].remove(websocket)
            if not self.active_connections[room_code]:
                del self.active_connections[room_code]

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_text(json.dumps(message))
        except:
            pass

    async def broadcast(self, message: dict, room_code: str, exclude: WebSocket = None):
        if room_code in self.active_connections:
            for connection in self.active_connections[room_code]:
                if connection != exclude:
                    try:
                        await connection.send_text(json.dumps(message))
                    except:
                        self.disconnect(connection, room_code)

manager = ConnectionManager()

def generate_room_code():
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(4))

def check_win(board: List[str], board_size: str) -> str:
    size = int(board_size[0])
    
    # Check rows
    for i in range(0, size*size, size):
        for j in range(size - 2):
            if board[i+j] and board[i+j] == board[i+j+1] == board[i+j+2]:
                return board[i+j]
    
    # Check columns
    for i in range(size):
        for j in range(0, size-2):
            if board[i+j*size] and board[i+j*size] == board[i+(j+1)*size] == board[i+(j+2)*size]:
                return board[i+j*size]
    
    # Check diagonals
    for i in range(0, (size-2)*size, size):
        for j in range(size-2):
            if board[i+j] and board[i+j] == board[i+j+size+1] == board[i+j+2*size+2]:
                return board[i+j]
    
    # Check anti-diagonals
    for i in range(0, (size-2)*size, size):
        for j in range(2, size):
            if board[i+j] and board[i+j] == board[i+j+size-1] == board[i+j+2*size-2]:
                return board[i+j]
    
    # Check tie
    if '' not in board:
        return 'T'
    
    return None

@app.get("/")
async def root():
    return {"message": "Tic-Tac-Toe Server is running"}

@app.post("/create")
async def create_room(request: Request):
    data = await request.json()
    board_size = data.get("board_size", "3x3")
    
    room_code = generate_room_code()
    while room_code in manager.game_rooms:
        room_code = generate_room_code()
    
    manager.game_rooms[room_code] = {
        "board": [''] * (int(board_size[0]) ** 2),
        "players": [],
        "turn": "X",
        "status": "waiting",
        "board_size": board_size,
        "created_at": time.time()
    }
    
    return {"code": room_code, "board_size": board_size}

@app.get("/room/{room_code}")
async def get_room(room_code: str):
    if room_code not in manager.game_rooms:
        raise HTTPException(status_code=404, detail="Room not found")
    return manager.game_rooms[room_code]

@app.websocket("/ws/{room_code}")
async def websocket_endpoint(websocket: WebSocket, room_code: str):
    if room_code not in manager.game_rooms:
        await websocket.close()
        return

    await manager.connect(websocket, room_code)
    room = manager.game_rooms[room_code]
    player_name = websocket.query_params.get("name", "Player")

    try:
        # Add player to room
        if len(room["players"]) < 2:
            player_symbol = "X" if len(room["players"]) == 0 else "O"
            room["players"].append({
                "websocket": websocket,
                "name": player_name,
                "symbol": player_symbol
            })

            # Send waiting message to first player
            if len(room["players"]) == 1:
                await manager.send_personal_message({
                    "type": "waiting",
                    "your_symbol": player_symbol,
                    "board": room["board"],
                    "turn": room["turn"],
                    "board_size": room["board_size"]
                }, websocket)
            else:
                # Start game when second player joins
                room["status"] = "playing"
                for i, player in enumerate(room["players"]):
                    opponent = room["players"][1-i]["name"]
                    await manager.send_personal_message({
                        "type": "ready",
                        "your_symbol": player["symbol"],
                        "opponent": opponent,
                        "board": room["board"],
                        "turn": room["turn"],
                        "board_size": room["board_size"]
                    }, player["websocket"])

        # Handle messages
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message["type"] == "move":
                await handle_move(room_code, websocket, message)
            elif message["type"] == "rematch":
                await handle_rematch(room_code, websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket, room_code)
        # Remove player from room
        room["players"] = [p for p in room["players"] if p["websocket"] != websocket]
        if room["players"]:
            await manager.send_personal_message({
                "type": "error",
                "msg": "Opponent disconnected"
            }, room["players"][0]["websocket"])

async def handle_move(room_code: str, websocket: WebSocket, message: dict):
    room = manager.game_rooms[room_code]
    player_index = next((i for i, p in enumerate(room["players"]) if p["websocket"] == websocket), -1)
    
    if player_index == -1:
        return

    player_symbol = room["players"][player_index]["symbol"]
    move_index = message["index"]

    # Validate move
    if (room["turn"] == player_symbol and 
        room["status"] == "playing" and 
        0 <= move_index < len(room["board"]) and 
        room["board"][move_index] == ''):
        
        # Make move
        room["board"][move_index] = player_symbol
        
        # Check win condition
        winner = check_win(room["board"], room["board_size"])
        
        if winner:
            room["status"] = "finished"
            await manager.broadcast({
                "type": "game_end",
                "board": room["board"],
                "winner": winner,
                "message": "Draw!" if winner == "T" else f"{winner} wins!"
            }, room_code)
        else:
            # Switch turn
            room["turn"] = "O" if room["turn"] == "X" else "X"
            await manager.broadcast({
                "type": "move_made",
                "board": room["board"],
                "turn": room["turn"],
                "player": room["players"][player_index]["name"]
            }, room_code)

async def handle_rematch(room_code: str, websocket: WebSocket):
    room = manager.game_rooms[room_code]
    
    if room["status"] == "finished":
        # Reset game
        size = int(room["board_size"][0])
        room["board"] = [''] * (size * size)
        room["turn"] = "X"
        room["status"] = "playing"
        
        await manager.broadcast({
            "type": "move_made",
            "board": room["board"],
            "turn": room["turn"],
            "message": "Rematch started!"
        }, room_code)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
