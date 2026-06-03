import os
import logging
import csv
import io
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import ContextTypes
import database
from game_logic import roll_dice, one_minute_warning_job, end_game_job, force_end_game

logger = logging.getLogger(__name__)

async def is_group_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.effective_chat.type == 'private':
        await update.message.reply_text("This command can only be used in a group chat.")
        return False
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        if member.status not in ['administrator', 'creator']:
            await update.message.reply_text("You must be a group admin to use this command.")
            return False
        return True
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False

async def listdice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private':
        return await update.message.reply_text("This command can only be used in a group chat.")
    chat_id = update.effective_chat.id
    actions = await database.get_dice_faces(chat_id, 'action')
    subjects = await database.get_dice_faces(chat_id, 'subject')
    text = "*Current Actions:*\n" + "\n".join([f"- {a}" for a in actions]) + "\n\n"
    text += "*Current Subjects:*\n" + "\n".join([f"- {s}" for s in subjects])
    await update.message.reply_text(text, parse_mode="Markdown")

async def addaction_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_group_admin(update, context):
        return
    group = await database.get_or_create_group(update.effective_chat.id, update.effective_chat.title, update.effective_user.id)
    if not group.get('is_premium'):
        return await update.message.reply_text("This feature requires the Premium upgrade. Use /upgrade to unlock!")
        
    value = " ".join(context.args)
    if not value:
        return await update.message.reply_text("Usage: /addaction <text>")
    if await database.add_dice_face(update.effective_chat.id, 'action', value):
        await update.message.reply_text(f"✅ Added action: {value}")
    else:
        await update.message.reply_text("❌ Action already exists.")

async def removeaction_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_group_admin(update, context):
        return
    group = await database.get_or_create_group(update.effective_chat.id, update.effective_chat.title, update.effective_user.id)
    if not group.get('is_premium'):
        return await update.message.reply_text("This feature requires the Premium upgrade. Use /upgrade to unlock!")
        
    value = " ".join(context.args)
    if not value:
        return await update.message.reply_text("Usage: /removeaction <text>")
    if await database.remove_dice_face(update.effective_chat.id, 'action', value):
        await update.message.reply_text(f"✅ Removed action: {value}")
    else:
        await update.message.reply_text("❌ Action not found.")

async def addsubject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_group_admin(update, context):
        return
    group = await database.get_or_create_group(update.effective_chat.id, update.effective_chat.title, update.effective_user.id)
    if not group.get('is_premium'):
        return await update.message.reply_text("This feature requires the Premium upgrade. Use /upgrade to unlock!")
        
    value = " ".join(context.args)
    if not value:
        return await update.message.reply_text("Usage: /addsubject <text>")
    if await database.add_dice_face(update.effective_chat.id, 'subject', value):
        await update.message.reply_text(f"✅ Added subject: {value}")
    else:
        await update.message.reply_text("❌ Subject already exists.")

async def removesubject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_group_admin(update, context):
        return
    group = await database.get_or_create_group(update.effective_chat.id, update.effective_chat.title, update.effective_user.id)
    if not group.get('is_premium'):
        return await update.message.reply_text("This feature requires the Premium upgrade. Use /upgrade to unlock!")
        
    value = " ".join(context.args)
    if not value:
        return await update.message.reply_text("Usage: /removesubject <text>")
    if await database.remove_dice_face(update.effective_chat.id, 'subject', value):
        await update.message.reply_text(f"✅ Removed subject: {value}")
    else:
        await update.message.reply_text("❌ Subject not found.")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private':
        await update.message.reply_text("Hello! Add me to a group to play the Kinky Dice Game. Once added, run /start in the group to register it to your account.")
    else:
        await database.get_or_create_group(
            update.effective_chat.id, 
            update.effective_chat.title or "Unknown Group",
            update.effective_user.id
        )
        await update.message.reply_text("Kinky Dice Game Bot is ready! The person who ran /start is now the registered owner. Use /playdicegame to start.")

async def playdicegame_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_chat.type == 'private':
        await update.message.reply_text("This game can only be played in a group.")
        return

    active_game = await database.get_active_game(chat_id)
    if active_game:
        await update.message.reply_text("A game is already active in this group!")
        return

    group = await database.get_or_create_group(chat_id, update.effective_chat.title or "Unknown Group")
    minutes = group['default_game_time']
    
    if context.args and context.args[0].isdigit():
        minutes = int(context.args[0])

    if not group['is_premium'] and minutes > 30:
        minutes = 30
        await update.message.reply_text("Free tier is limited to a maximum of 30 minutes per game. Starting a 30-minute game.")

    end_time = datetime.now() + timedelta(minutes=minutes)
    
    keyboard = [[InlineKeyboardButton("🎲 Roll the Dice", callback_data="roll_dice")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    announcement = await update.message.reply_text(
        f"🎲 *A new Kinky Dice Game has started!* 🎲\n\n"
        f"The game will last for {minutes} minutes.\n"
        f"Click the button below to roll your challenge!",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

    game_id = await database.create_game(chat_id, end_time, announcement.message_id)

    # Schedule jobs
    context.job_queue.run_once(
        end_game_job, 
        when=minutes * 60, 
        chat_id=chat_id, 
        data={'game_id': game_id},
        name=f"end_game_{game_id}"
    )

    if minutes > 1:
        context.job_queue.run_once(
            one_minute_warning_job,
            when=(minutes - 1) * 60,
            chat_id=chat_id,
            name=f"warn_game_{game_id}"
        )

async def stopdicegame_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private':
        return await update.message.reply_text("This command can only be used in a group chat.")
        
    chat_id = update.effective_chat.id
    
    # Verify group admin
    if not await is_group_admin(update, context):
        return

    game = await database.get_active_game(chat_id)
    if not game:
        return await update.message.reply_text("There is no active game to stop.")
        
    # Cancel scheduled jobs for this chat
    for job in context.job_queue.jobs():
        if getattr(job, 'chat_id', None) == chat_id:
            job.schedule_removal()
            
    await force_end_game(context.bot, chat_id, game['game_id'])

async def execute_roll(chat_id: int, player_id: int, user_mention: str, chat_title: str, bot, respond_func):
    active_game = await database.get_active_game(chat_id)
    if not active_game:
        await respond_func("No active game right now.")
        return

    group = await database.get_or_create_group(chat_id, chat_title or "Unknown Group")
    cooldown_mins = group['cooldown_minutes']
    
    last_roll_str = await database.get_player_cooldown(player_id, chat_id)
    now = datetime.now()
    
    if last_roll_str:
        last_roll = datetime.fromisoformat(last_roll_str)
        if now < last_roll + timedelta(minutes=cooldown_mins):
            remaining = (last_roll + timedelta(minutes=cooldown_mins) - now).total_seconds() / 60
            if respond_func.__code__.co_argcount == 2 and "show_alert" in respond_func.__code__.co_varnames:
                await respond_func(f"You must wait {remaining:.1f} minutes before rolling again.", show_alert=True)
            else:
                await respond_func(f"You must wait {remaining:.1f} minutes before rolling again.")
            return

    await database.update_player_cooldown(player_id, chat_id, now.isoformat())

    action, subject = await roll_dice(chat_id)
    
    text = (f"🎲 {user_mention} rolled the dice!\n\n"
            f"<b>Action:</b> {action}\n"
            f"<b>Subject:</b> {subject}\n\n"
            f"Reply to THIS MESSAGE with your submission!")
            
    await bot.send_message(
        chat_id=chat_id, 
        text=text, 
        parse_mode="HTML"
    )

async def roll_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    async def respond_func(text: str, show_alert=False):
        await query.answer(text, show_alert=show_alert)
        
    await execute_roll(
        update.effective_chat.id,
        update.effective_user.id,
        update.effective_user.mention_html(),
        update.effective_chat.title,
        context.bot,
        respond_func
    )

async def roll_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private':
        return await update.message.reply_text("This command can only be used in a group chat.")

    async def respond_func(text: str):
        await update.message.reply_text(text)
        
    await execute_roll(
        update.effective_chat.id,
        update.effective_user.id,
        update.effective_user.mention_html(),
        update.effective_chat.title,
        context.bot,
        respond_func
    )

async def handle_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or update.edited_message
    if not message or not message.reply_to_message or message.reply_to_message.from_user.id != context.bot.id:
        return
        
    chat_id = update.effective_chat.id
    active_game = await database.get_active_game(chat_id)
    
    if not active_game:
        return

    if not (message.photo or message.video or message.voice or message.audio or message.text):
        return

    player_id = message.from_user.id
    player_name = message.from_user.full_name
    
    submission_id = await database.create_submission(
        game_id=active_game['game_id'], 
        player_id=player_id, 
        player_name=player_name, 
        message_id=message.message_id
    )

    keyboard = []
    row1 = [InlineKeyboardButton(str(i), callback_data=f"rate_{submission_id}_{i}") for i in range(1, 6)]
    row2 = [InlineKeyboardButton(str(i), callback_data=f"rate_{submission_id}_{i}") for i in range(6, 11)]
    keyboard.append(row1)
    keyboard.append(row2)
    keyboard.append([InlineKeyboardButton("🎲 Roll the Dice", callback_data="roll_dice")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(
        f"Submission received! Everyone, rate {player_name}'s post (1-10):",
        reply_markup=reply_markup
    )

async def rate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    data = query.data.split('_') 
    if len(data) != 3:
        return
        
    submission_id = int(data[1])
    score = int(data[2])
    voter_id = update.effective_user.id
    
    success = await database.add_vote(submission_id, voter_id, score)
    
    if success:
        await query.answer(f"You rated it a {score}!")
    else:
        await query.answer("You have already voted on this submission!", show_alert=True)

async def upgrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"UPGRADE COMMAND TRIGGERED by {update.effective_user.id} in {update.effective_chat.id}")
    if update.effective_chat.type == 'private':
        return await update.message.reply_text("Please run this command in a group chat.")
        
    chat_id = update.effective_chat.id
    
    if not await is_group_admin(update, context):
        return

    group = await database.get_or_create_group(chat_id, update.effective_chat.title)
    
    # Check if the group is already owned by someone else
    if group.get('owner_id') and group['owner_id'] != update.effective_user.id:
        return await update.message.reply_text("Only the registered bot owner for this group can purchase upgrades. The owner is the person who first typed /start when installing the bot.")
        
    # If no owner yet, register this admin as the owner
    if not group.get('owner_id'):
        group = await database.get_or_create_group(chat_id, update.effective_chat.title, update.effective_user.id)

    if group.get('is_premium'):
        return await update.message.reply_text("This group is already Premium! 🌟")

    group_cost = int(os.getenv("GROUP_UPGRADE_COST", "200"))
    account_cost = int(os.getenv("ACCOUNT_UPGRADE_COST", "1000"))
    bypass_code = os.getenv("UPGRADE_BYPASS_CODE")

    if context.args and len(context.args) > 0:
        if bypass_code and context.args[0] == bypass_code:
            await database.set_user_account_license(update.effective_user.id)
            await database.set_group_premium(chat_id)
            await update.message.reply_text("🌟 **Bypass Code Accepted!** You now hold an Account License. All your groups are Premium!", parse_mode="Markdown")
            return
        else:
            await update.message.reply_text("❌ Invalid bypass code.")
            return

    keyboard = [
        [InlineKeyboardButton(f"Upgrade Group ({group_cost} ⭐)", callback_data=f"upgrade_group_{chat_id}")],
        [InlineKeyboardButton(f"Account License ({account_cost} ⭐)", callback_data=f"upgrade_account_{chat_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🌟 **Unlock Premium Features!** 🌟\n\n"
        "Premium unlocks custom Actions, Subjects, and game durations >30 mins.\n"
        "Choose an upgrade path:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def upgrade_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    if len(data) != 3 or data[0] != "upgrade":
        return
        
    action = data[1] # 'group' or 'account'
    chat_id = int(data[2])
    
    if action == "group":
        title = "Premium Group Upgrade"
        description = "Unlocks premium features for this specific group."
        payload = f"upgrade-group-{chat_id}"
        price = int(os.getenv("GROUP_UPGRADE_COST", "200"))
    elif action == "account":
        title = "Premium Account License"
        description = "Unlocks premium features for all groups you own!"
        payload = f"upgrade-account-{chat_id}"
        price = int(os.getenv("ACCOUNT_UPGRADE_COST", "1000"))
    else:
        return

    prices = [LabeledPrice("Premium", price)]
    
    await context.bot.send_invoice(
        chat_id=update.effective_user.id, # Send invoice to DM
        title=title,
        description=description,
        payload=payload,
        provider_token="", # Empty for Telegram Stars
        currency="XTR",
        prices=prices
    )
    await query.edit_message_text(f"An invoice has been sent to your private messages to purchase the {title}!")

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    if query.invoice_payload.startswith("upgrade-"):
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Unknown payload")

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    
    parts = payload.split('-')
    if len(parts) == 3 and parts[0] == "upgrade":
        upgrade_type = parts[1]
        chat_id = int(parts[2])
        user_id = update.effective_user.id
        
        if upgrade_type == "group":
            await database.set_group_premium(chat_id)
            await update.message.reply_text("Thank you for your purchase! 🌟 This group is now Premium!")
            try:
                await context.bot.send_message(chat_id=chat_id, text="🌟 **Success!** This group has been upgraded to Premium! You can now customize dice and set longer game times.", parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Failed to send success msg to group: {e}")
        elif upgrade_type == "account":
            await database.set_user_account_license(user_id)
            # Re-fetch or create group to apply the new account license logic automatically
            await database.get_or_create_group(chat_id)
            await update.message.reply_text("Thank you for your purchase! 🌟 You now hold an Account License. All your groups are Premium!")
            try:
                await context.bot.send_message(chat_id=chat_id, text="🌟 **Success!** The group owner has purchased an Account License! This group is now Premium!", parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Failed to send success msg to group: {e}")

async def botstats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    global_admin_id = os.getenv("GLOBAL_ADMIN_ID")
    
    is_global_admin = False
    if global_admin_id and str(user_id) == str(global_admin_id):
        is_global_admin = True

    if is_global_admin:
        if context.args and context.args[0].lower() == 'export':
            groups = await database.get_all_groups_list()
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['Group ID', 'Title', 'Owner ID', 'Premium Status', 'Owner Has Account License'])
            for g in groups:
                writer.writerow([
                    g['group_id'], 
                    g['group_title'], 
                    g['owner_id'], 
                    bool(g['is_premium']), 
                    bool(g['has_account_license'])
                ])
            
            output.seek(0)
            await update.message.reply_document(
                document=output.getvalue().encode('utf-8'),
                filename=f"dice_bot_groups_{datetime.now().strftime('%Y%m%d')}.csv"
            )
            return

        stats = await database.get_global_stats()
        await update.message.reply_text(
            f"📊 **Global Bot Stats** 📊\n\n"
            f"**Total Groups:** {stats['total_groups']}\n"
            f"**Total Games Run:** {stats['total_games']}\n"
            f"**Avg Games/Group:** {stats['avg_games_per_group']}\n\n"
            f"*(Type `/botstats export` to download the raw group list)*",
            parse_mode="Markdown"
        )
    else:
        stats = await database.get_owner_stats(user_id)
        license_status = "✅ Active" if stats['has_account_license'] else "❌ None"
        await update.message.reply_text(
            f"📊 **Your Bot Stats** 📊\n\n"
            f"**Your Account License:** {license_status}\n"
            f"**Groups Owned:** {stats['total_owned_groups']}\n"
            f"**Total Games in Your Groups:** {stats['total_owned_games']}\n",
            parse_mode="Markdown"
        )
