import os
import logging
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, PreCheckoutQueryHandler, filters
import database
import handlers
from datetime import datetime
from game_logic import end_game_job, one_minute_warning_job

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def post_init(application):
    logger.info("Initializing database...")
    await database.init_db()
    
    logger.info("Restoring active game timers...")
    active_games = await database.get_all_active_games()
    now = datetime.now()
    restored = 0
    for game in active_games:
        try:
            end_time = datetime.fromisoformat(game['end_time'])
            remaining = (end_time - now).total_seconds()
            
            if remaining <= 0:
                # Game should have already ended, end it immediately
                application.job_queue.run_once(
                    end_game_job,
                    when=1,
                    chat_id=game['group_id'],
                    data={'game_id': game['game_id']},
                    name=f"end_game_{game['game_id']}"
                )
            else:
                # Schedule end game
                application.job_queue.run_once(
                    end_game_job,
                    when=remaining,
                    chat_id=game['group_id'],
                    data={'game_id': game['game_id']},
                    name=f"end_game_{game['game_id']}"
                )
                # Schedule 1 minute warning if > 1 min remaining
                if remaining > 60:
                    application.job_queue.run_once(
                        one_minute_warning_job,
                        when=remaining - 60,
                        chat_id=game['group_id'],
                        name=f"warn_game_{game['game_id']}"
                    )
            restored += 1
        except Exception as e:
            logger.error(f"Failed to restore timer for game {game['game_id']}: {e}")
            
    logger.info(f"Restored {restored} active game timers.")

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
