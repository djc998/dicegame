import random
from telegram.ext import CallbackContext
import database

async def roll_dice(group_id: int):
    """Returns a tuple of (action, subject) fetched from the database."""
    actions = await database.get_dice_faces(group_id, 'action')
    subjects = await database.get_dice_faces(group_id, 'subject')
    
    action = random.choice(actions) if actions else "No Actions Configured"
    subject = random.choice(subjects) if subjects else "No Subjects Configured"
    return action, subject

async def one_minute_warning_job(context: CallbackContext):
    """Job executed 1 minute before the game ends."""
    job = context.job
    chat_id = job.chat_id
    await context.bot.send_message(
        chat_id=chat_id,
        text="⚠️ **1 Minute Remaining!** ⚠️\nSubmit your media and cast your votes!",
        parse_mode="Markdown"
    )

async def force_end_game(bot, chat_id: int, game_id: int):
    # Mark game as inactive in the database
    await database.end_game(game_id)
    
    # Calculate winner
    top_submission = await database.get_top_submission(game_id)
    
    if top_submission:
        player_name = top_submission['player_name']
        avg_score = top_submission['avg_score']
        text = (f"🏁 **The Game is Over!** 🏁\n\n"
                f"🎉 The winner is **{player_name}** with an average score of **{avg_score:.1f}/10**! 🎉")
        await bot.send_message(
            chat_id=chat_id, 
            text=text, 
            reply_to_message_id=top_submission['message_id'],
            parse_mode="Markdown"
        )
    else:
        text = "🏁 **The Game is Over!** 🏁\n\nNo submissions were rated. Better luck next time!"
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")

async def end_game_job(context: CallbackContext):
    """Job executed when the game timer expires."""
    job = context.job
    await force_end_game(context.bot, job.chat_id, job.data['game_id'])
