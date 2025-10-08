import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация - НИКОГДА не пиши токен в коде!
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Добавишь в Render как переменную окружения
WEB_APP_URL = "https://strike-boy.github.io/tic-tac-toe_new/"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("🎮 Играть в Tic-Tac-Toe", web_app={"url": WEB_APP_URL})]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Добро пожаловать в NEON Tic-Tac-Toe! 🎮\n\n"
        "Нажми кнопку ниже чтобы начать игру:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = (
        "🎮 *NEON Tic-Tac-Toe*\n\n"
        "🌟 *Возможности:*\n"
        "• 🤖 Игра с ИИ разных уровней\n" 
        "• 👥 Локальная игра на одном устройстве\n"
        "• 🌐 Онлайн-игра с друзьями\n"
        "• 💬 Чат во время игры\n\n"
        "🎯 *Как играть онлайн:*\n"
        "1. Создай комнату в игре\n"
        "2. Поделись кодом с другом\n"
        "3. Наслаждайтесь игрой!\n\n"
        "⚡ *Управление:*\n"
        "• Просто нажимай на клетки\n"
        "• Используй кнопку рестарт для новой игры"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

def main():
    """Запуск бота"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен!")
        return
        
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    
    # Запускаем бота
    logger.info("Бот запущен!")
    application.run_polling()

if __name__ == "__main__":
    main()
