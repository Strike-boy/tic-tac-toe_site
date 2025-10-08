import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv("8461263670:AAHNklJHXKbnz94WUpau1TH1CVfMy1saW6o")  # Получи у @BotFather
WEB_APP_URL = "https://strike-boy.github.io/tic-tac-toe_new/"  # URL твоего фронтенда

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("🎮 Играть в Tic-Tac-Toe", web_app={"url": WEB_APP_URL})],
        [InlineKeyboardButton("👥 Создать комнату", callback_data="create_room")],
        [InlineKeyboardButton("📋 Помощь", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Добро пожаловать в NEON Tic-Tac-Toe! 🎮\n\n"
        "Выбери действие:",
        reply_markup=reply_markup
    )

async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка данных из Web App"""
    try:
        data = update.effective_message.web_app_data.data
        logger.info(f"Received web app data: {data}")
        # Здесь можно обработать данные из игры
    except Exception as e:
        logger.error(f"Error handling web app data: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "create_room":
        # Создаем уникальную ссылку для комнаты
        web_app_url = f"{WEB_APP_URL}?startapp=create"
        keyboard = [
            [InlineKeyboardButton("🎮 Открыть игру", web_app={"url": web_app_url})],
            [InlineKeyboardButton("📤 Поделиться игрой", switch_inline_query="🎯 Сыграем в Tic-Tac-Toe!")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🎮 Готов создать игровую комнату!\n\n"
            "Нажми кнопку ниже чтобы начать:",
            reply_markup=reply_markup
        )
    
    elif query.data == "help":
        await query.edit_message_text(
            "🎮 *NEON Tic-Tac-Toe*\n\n"
            "🌟 *Возможности:*\n"
            "• 🤖 Игра с ИИ разных уровней\n"
            "• 👥 Локальная игра на одном устройстве\n"
            "• 🌐 Онлайн-игра с друзьями\n"
            "• 💬 Чат во время игры\n\n"
            "🎯 *Как играть онлайн:*\n"
            "1. Создай комнату\n"
            "2. Поделись кодом с другом\n"
            "3. Наслаждайтесь игрой!\n\n"
            "⚡ *Управление:*\n"
            "• Просто нажимай на клетки\n"
            "• Используй кнопку рестарт для новой игры",
            parse_mode="Markdown"
        )

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline запросов"""
    query = update.inline_query.query
    results = []
    
    # Создаем результат для быстрого старта игры
    keyboard = [[InlineKeyboardButton("🎮 Играть", web_app={"url": WEB_APP_URL})]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    results.append(InlineQueryResultArticle(
        id="1",
        title="🎮 NEON Tic-Tac-Toe",
        description="Сыграем в крутые крестики-нолики?",
        input_message_content=InputTextMessageContent(
            message_text="🎯 *Привет! Сыграем в Tic-Tac-Toe?*\n\n"
                        "Нажми кнопку ниже чтобы начать игру! 🎮",
            parse_mode="Markdown"
        ),
        reply_markup=reply_markup
    ))
    
    await update.inline_query.answer(results)

def main():
    """Запуск бота"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(InlineQueryHandler(inline_query))
    
    # Запускаем бота
    logger.info("Бот запущен!")
    application.run_polling()

if __name__ == "__main__":
    main()
