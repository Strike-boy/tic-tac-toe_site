# server.py
import time
import secrets
import string
import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List, Set, Optional
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Neon Tic-Tac-Toe API", version="2.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Модели данных
class GameRoom:
    def __init__(self, code: str, board_size: str = "3x3"):
        self.code = code
        self.board_size = board_size
        self.sockets: List[WebSocket] = []
        self.players: List[dict] = []
        self.board: List[str] = []
        self.turn: str = "X"
        self.state: str = "waiting"  # waiting, playing, finished
        self.created: float = time.time()
        self.rematch_votes: Set[WebSocket] = set()
        self.messages: List[dict] = []
        self.win_condition: int = 3  # Количество в ряд для победы
        
        # Инициализация доски в зависимости от размера
        size = int(board_size[0])
        self.board = [''] * (size * size)
        
        # Установка условий победы
        if board_size == "4x4":
            self.win_condition = 3
        elif board_size == "5x5":
            self.win_condition = 4
        else:
            self.win_condition = 3

    def to_dict(self):
        return {
            "code": self.code,
            "board_size": self.board_size,
            "players": self.players,
            "board": self.board,
            "turn": self.turn,
            "state": self.state,
            "player_count": len(self.players),
            "win_condition": self.win_condition
        }

# Глобальное хранилище игр
games: Dict[str, GameRoom] = {}

def gen_code(length: int = 4) -> str:
    """Генерация уникального кода комнаты"""
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(secrets.choice(alphabet) for _ in range(length))
        if code not in games:
            return code

def check_win(board: List[str], win_condition: int, board_size: int) -> Optional[str]:
    """
    Проверка победы для доски любого размера
    """
    size = board_size
    
    # Проверка строк
    for row in range(size):
        for col in range(size - win_condition + 1):
            if board[row * size + col] and all(
                board[row * size + col + i] == board[row * size + col] 
                for i in range(win_condition)
            ):
                return board[row * size + col]

    # Проверка столбцов
    for col in range(size):
        for row in range(size - win_condition + 1):
            if board[row * size + col] and all(
                board[(row + i) * size + col] == board[row * size + col] 
                for i in range(win_condition)
            ):
                return board[row * size + col]

    # Проверка диагоналей (слева направо)
    for row in range(size - win_condition + 1):
        for col in range(size - win_condition + 1):
            if board[row * size + col] and all(
                board[(row + i) * size + col + i] == board[row * size + col] 
                for i in range(win_condition)
            ):
                return board[row * size + col]

    # Проверка диагоналей (справа налево)
    for row in range(size - win_condition + 1):
        for col in range(win_condition - 1, size):
            if board[row * size + col] and all(
                board[(row + i) * size + col - i] == board[row * size + col] 
                for i in range(win_condition)
            ):
                return board[row * size + col]

    # Проверка ничьи
    if '' not in board:
        return 'D'
    
    return None

async def send_safe(websocket: WebSocket, payload: dict):
    """Безопасная отправка сообщения"""
    try:
        await websocket.send_text(json.dumps(payload))
    except Exception as e:
        logger.warning(f"Failed to send message: {e}")

async def broadcast_room(room: GameRoom, payload: dict, exclude: WebSocket = None):
    """Отправка сообщения всем игрокам в комнате"""
    disconnected = []
    for ws in room.sockets:
        if ws != exclude:
            try:
                await send_safe(ws, payload)
            except:
                disconnected.append(ws)
    
    # Удаляем отключившиеся сокеты
    for ws in disconnected:
        if ws in room.sockets:
            idx = room.sockets.index(ws)
            room.sockets.remove(ws)
            room.players.pop(idx)

# API endpoints
@app.get("/")
async def root():
    """Корневой endpoint для проверки работы сервера"""
    return {
        "message": "Neon Tic-Tac-Toe Server v2.0", 
        "status": "online",
        "active_rooms": len(games),
        "timestamp": time.time()
    }

@app.post("/create")
async def create_room(request: Request):
    """Создание новой игровой комнаты"""
    try:
        data = await request.json()
        board_size = data.get("board_size", "3x3")
    except:
        board_size = "3x3"
    
    # Валидация размера доски
    if board_size not in ["3x3", "4x4", "5x5"]:
        board_size = "3x3"
    
    code = gen_code()
    games[code] = GameRoom(code, board_size)
    
    logger.info(f"Room created: {code} (Size: {board_size})")
    return {"code": code, "board_size": board_size}

@app.get("/room/{code}")
async def get_room_info(code: str):
    """Получение информации о комнате"""
    room = games.get(code)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return room.to_dict()

@app.get("/room/{code}/status")
async def get_room_status(code: str):
    """Статус комнаты для мониторинга"""
    room = games.get(code)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return {
        "players": len(room.players),
        "state": room.state,
        "board_size": room.board_size,
        "player_names": [p["name"] for p in room.players]
    }

@app.get("/rooms")
async def list_rooms():
    """Список всех активных комнат (для администрирования)"""
    return {
        "active_rooms": len(games),
        "rooms": [
            {
                "code": room.code,
                "players": len(room.players),
                "state": room.state,
                "board_size": room.board_size,
                "created": room.created
            }
            for room in games.values()
        ]
    }

@app.websocket("/ws/{code}")
async def websocket_endpoint(websocket: WebSocket, code: str):
    """WebSocket endpoint для игрового процесса"""
    await websocket.accept()
    
    # Получаем параметры подключения
    name = websocket.query_params.get("name", "Player")
    logger.info(f"Player {name} connecting to room {code}")
    
    # Проверяем существование комнаты
    room = games.get(code)
    if not room:
        await send_safe(websocket, {
            "type": "error", 
            "msg": "Room not found"
        })
        await websocket.close()
        return
    
    # Проверяем наличие места в комнате
    if len(room.sockets) >= 2:
        await send_safe(websocket, {
            "type": "error", 
            "msg": "Room is full"
        })
        await websocket.close()
        return
    
    # Определяем символ игрока
    symbol = "X" if len(room.sockets) == 0 else "O"
    
    # Добавляем игрока в комнату
    room.sockets.append(websocket)
    room.players.append({"name": name, "symbol": symbol})
    
    # Отправляем историю чата новому игроку
    if room.messages:
        await send_safe(websocket, {
            "type": "chat_history",
            "messages": room.messages[-20:]  # Последние 20 сообщений
        })
    
    # Обрабатываем подключение
    if len(room.sockets) == 1:
        # Первый игрок - ожидаем второго
        await send_safe(websocket, {
            "type": "waiting",
            "your_symbol": symbol,
            "board": room.board,
            "turn": room.turn,
            "board_size": room.board_size,
            "win_condition": room.win_condition,
            "opponent": None
        })
    else:
        # Второй игрок - начинаем игру
        room.state = "playing"
        player1, player2 = room.players[0], room.players[1]
        
        # Уведомляем первого игрока
        await send_safe(room.sockets[0], {
            "type": "ready",
            "your_symbol": player1["symbol"],
            "opponent": player2["name"],
            "board": room.board,
            "turn": room.turn,
            "board_size": room.board_size,
            "win_condition": room.win_condition
        })
        
        # Уведомляем второго игрока
        await send_safe(room.sockets[1], {
            "type": "ready",
            "your_symbol": player2["symbol"],
            "opponent": player1["name"],
            "board": room.board,
            "turn": room.turn,
            "board_size": room.board_size,
            "win_condition": room.win_condition
        })
        
        # Уведомляем о подключении
        await broadcast_room(room, {
            "type": "player_joined",
            "player_name": name,
            "message": f"{name} joined the game"
        })
    
    try:
        # Основной цикл обработки сообщений
        while True:
            # Получаем сообщение
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
            except Exception as e:
                logger.warning(f"Message parse error: {e}")
                continue
            
            # Обрабатываем тип сообщения
            msg_type = message.get("type")
            
            if msg_type == "move":
                await handle_move(room, websocket, message)
                
            elif msg_type == "chat":
                await handle_chat(room, websocket, message)
                
            elif msg_type == "rematch":
                await handle_rematch(room, websocket)
                
            elif msg_type == "emoji":
                await handle_emoji(room, websocket, message)
                
    except WebSocketDisconnect:
        logger.info(f"Player {name} disconnected from room {code}")
        await handle_disconnect(room, websocket, name)
    except Exception as e:
        logger.error(f"WebSocket error in room {code}: {e}")
        await handle_disconnect(room, websocket, name)

async def handle_move(room: GameRoom, websocket: WebSocket, message: dict):
    """Обработка хода игрока"""
    try:
        idx = int(message.get("index", -1))
        board_size = int(room.board_size[0])
        
        # Проверка валидности хода
        if idx < 0 or idx >= len(room.board):
            await send_safe(websocket, {
                "type": "error", 
                "msg": "Invalid move index"
            })
            return
        
        # Проверка что игрок в комнате
        if websocket not in room.sockets:
            return
        
        # Определяем игрока
        player_idx = room.sockets.index(websocket)
        player_symbol = room.players[player_idx]["symbol"]
        player_name = room.players[player_idx]["name"]
        
        # Проверка очереди хода
        if room.turn != player_symbol:
            await send_safe(websocket, {
                "type": "error", 
                "msg": "Not your turn"
            })
            return
        
        # Проверка что клетка свободна
        if room.board[idx] != '':
            await send_safe(websocket, {
                "type": "error", 
                "msg": "Cell already occupied"
            })
            return
        
        # Совершаем ход
        room.board[idx] = player_symbol
        
        # Проверяем победу
        winner = check_win(room.board, room.win_condition, int(room.board_size[0]))
        
        if winner:
            # Игра завершена
            room.state = "finished"
            winner_name = next(
                (p["name"] for p in room.players if p["symbol"] == winner), 
                winner
            )
            
            await broadcast_room(room, {
                "type": "game_end",
                "board": room.board,
                "winner": winner,
                "winner_name": winner_name,
                "message": "Draw!" if winner == "D" else f"{winner_name} wins!",
                "win_condition": room.win_condition
            })
            
        else:
            # Продолжаем игру
            room.turn = "O" if room.turn == "X" else "X"
            await broadcast_room(room, {
                "type": "move_made",
                "board": room.board,
                "turn": room.turn,
                "player": player_name,
                "position": idx,
                "win_condition": room.win_condition
            })
            
    except Exception as e:
        logger.error(f"Move handling error: {e}")
        await send_safe(websocket, {
            "type": "error", 
            "msg": "Internal server error"
        })

async def handle_chat(room: GameRoom, websocket: WebSocket, message: dict):
    """Обработка сообщений чата"""
    try:
        chat_message = message.get("message", "").strip()
        if not chat_message:
            return
        
        # Определяем отправителя
        if websocket in room.sockets:
            player_idx = room.sockets.index(websocket)
            sender_name = room.players[player_idx]["name"]
            
            # Сохраняем сообщение
            chat_data = {
                "sender": sender_name,
                "message": chat_message,
                "timestamp": time.time(),
                "type": "text"
            }
            room.messages.append(chat_data)
            
            # Рассылаем всем
            await broadcast_room(room, {
                "type": "chat_message",
                "sender": sender_name,
                "message": chat_message,
                "timestamp": chat_data["timestamp"]
            })
            
    except Exception as e:
        logger.error(f"Chat handling error: {e}")

async def handle_rematch(room: GameRoom, websocket: WebSocket):
    """Обработка запроса на реванш"""
    try:
        if room.state != "finished":
            await send_safe(websocket, {
                "type": "error", 
                "msg": "Game is not finished"
            })
            return
        
        # Добавляем голос за реванш
        room.rematch_votes.add(websocket)
        
        # Уведомляем о голосе
        if websocket in room.sockets:
            player_idx = room.sockets.index(websocket)
            player_name = room.players[player_idx]["name"]
            
            await broadcast_room(room, {
                "type": "rematch_vote",
                "player_name": player_name,
                "votes": len(room.rematch_votes),
                "required": 2
            })
        
        # Проверяем достаточно ли голосов
        if len(room.rematch_votes) >= 2:
            # Сбрасываем игру
            size = int(room.board_size[0])
            room.board = [''] * (size * size)
            room.turn = "X"
            room.state = "playing"
            room.rematch_votes.clear()
            
            # Уведомляем о начале реванша
            await broadcast_room(room, {
                "type": "rematch_start",
                "board": room.board,
                "turn": room.turn,
                "board_size": room.board_size,
                "win_condition": room.win_condition,
                "message": "Rematch started!"
            })
            
    except Exception as e:
        logger.error(f"Rematch handling error: {e}")

async def handle_emoji(room: GameRoom, websocket: WebSocket, message: dict):
    """Обработка эмодзи-реакций"""
    try:
        emoji = message.get("emoji", "")
        if not emoji:
            return
        
        if websocket in room.sockets:
            player_idx = room.sockets.index(websocket)
            sender_name = room.players[player_idx]["name"]
            
            await broadcast_room(room, {
                "type": "emoji_reaction",
                "sender": sender_name,
                "emoji": emoji,
                "timestamp": time.time()
            }, exclude=websocket)
            
    except Exception as e:
        logger.error(f"Emoji handling error: {e}")

async def handle_disconnect(room: GameRoom, websocket: WebSocket, player_name: str):
    """Обработка отключения игрока"""
    try:
        # Удаляем игрока из комнаты
        if websocket in room.sockets:
            idx = room.sockets.index(websocket)
            room.sockets.remove(websocket)
            room.players.pop(idx)
            
            # Удаляем голоса за реванш
            room.rematch_votes.discard(websocket)
            
            # Уведомляем оставшихся игроков
            if room.sockets:
                await send_safe(room.sockets[0], {
                    "type": "player_left",
                    "player_name": player_name,
                    "message": f"{player_name} left the game"
                })
                
                # Если игра была в процессе, завершаем её
                if room.state == "playing":
                    room.state = "finished"
                    await send_safe(room.sockets[0], {
                        "type": "game_ended",
                        "reason": "opponent_left",
                        "message": "Opponent left. You win!"
                    })
        
        # Если комната пустая, планируем её удаление
        if not room.sockets:
            await schedule_room_cleanup(room.code)
            
    except Exception as e:
        logger.error(f"Disconnect handling error: {e}")

async def schedule_room_cleanup(room_code: str):
    """Планирование удаления пустой комнаты"""
    await asyncio.sleep(300)  # 5 минут
    if room_code in games and not games[room_code].sockets:
        del games[room_code]
        logger.info(f"Room {room_code} cleaned up")

@app.delete("/room/{code}")
async def delete_room(code: str):
    """Принудительное удаление комнаты (для администрирования)"""
    if code in games:
        del games[code]
        return {"message": f"Room {code} deleted"}
    else:
        raise HTTPException(status_code=404, detail="Room not found")

@app.post("/cleanup")
async def cleanup_rooms():
    """Очистка неактивных комнат"""
    current_time = time.time()
    rooms_to_delete = []
    
    for code, room in games.items():
        # Удаляем комнаты без игроков старше 15 минут
        if not room.sockets and current_time - room.created > 900:
            rooms_to_delete.append(code)
    
    for code in rooms_to_delete:
        del games[code]
    
    return {
        "deleted_rooms": len(rooms_to_delete),
        "active_rooms": len(games),
        "message": f"Cleaned up {len(rooms_to_delete)} rooms"
    }

# Health check endpoint для мониторинга
@app.get("/health")
async def health_check():
    """Проверка здоровья сервера"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "active_rooms": len(games),
        "total_players": sum(len(room.players) for room in games.values())
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")