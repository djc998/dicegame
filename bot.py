import os
import logging
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, PreCheckoutQueryHandler, filters
import database
import handlers
import settings_handler

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def post_init(application):
    logger.info("Initializing database...")
    await database.init_db()

def main():
    load_dotenv()
    token = os.getenv("BOT_TOKEN")
    
    if not token or token == "your_bot_token_here":
        logger.error("BOT_TOKEN is not set in the .env file. Please add it and restart.")
        return

    application = ApplicationBuilder().token(token).post_init(post_init).build()

    # Add Handlers
    application.add_handler(CommandHandler("start", handlers.start_command))
    application.add_handler(CommandHandler("playdicegame", handlers.playdicegame_command))
    application.add_handler(CommandHandler("stopdicegame", handlers.stopdicegame_command))
    application.add_handler(CommandHandler("roll", handlers.roll_command))
    application.add_handler(CommandHandler("botstats", handlers.botstats_command))
    application.add_handler(CommandHandler("upgrade", handlers.upgrade_command))
    application.add_handler(CallbackQueryHandler(handlers.upgrade_callback, pattern="^upgrade_(group|account)_"))
    application.add_handler(PreCheckoutQueryHandler(handlers.precheckout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handlers.successful_payment_callback))
    
    # Admin commands
    application.add_handler(CommandHandler("listdice", handlers.listdice_command))
    application.add_handler(CommandHandler("addaction", handlers.addaction_command))
    application.add_handler(CommandHandler("removeaction", handlers.removeaction_command))
    application.add_handler(CommandHandler("addsubject", handlers.addsubject_command))
    application.add_handler(CommandHandler("removesubject", handlers.removesubject_command))
    
    # Global Admin Settings Menu
    application.add_handler(settings_handler.get_settings_handler())
    
    application.add_handler(CallbackQueryHandler(handlers.roll_callback, pattern="^roll_dice$"))
    application.add_handler(CallbackQueryHandler(handlers.rate_callback, pattern="^rate_"))
    
    # Message handler for replies (submissions)
    application.add_handler(MessageHandler(filters.REPLY & ~filters.COMMAND, handlers.handle_submission))

    logger.info("Starting bot...")
    application.run_polling()

if __name__ == '__main__':
    main()
