import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
import database

logger = logging.getLogger(__name__)

# States
SELECT_GROUP, SELECT_CATEGORY, MANAGE_ITEMS, WAITING_FOR_INPUT, WAITING_FOR_BULK_INPUT = range(5)

def is_admin(user_id: int) -> bool:
    # Deprecated: Now using multi-tenant ownership
    return True

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        await update.message.reply_text("Please use this command in a private message to me.")
        return ConversationHandler.END

    groups = await database.get_groups_by_owner(update.effective_user.id)
    if not groups:
        await update.message.reply_text("You are not the registered owner of any groups. Make sure you run /start inside the group first.")
        return ConversationHandler.END

    keyboard = []
    for g in groups:
        keyboard.append([InlineKeyboardButton(g['group_title'] or f"Group {g['group_id']}", callback_data=f"group_{g['group_id']}")])
    
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Please select a group you own to configure:", reply_markup=reply_markup)
    return SELECT_GROUP

async def group_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("Settings menu closed.")
        return ConversationHandler.END
        
    group_id = int(query.data.split('_')[1])
    context.user_data['settings_group_id'] = group_id
    
    keyboard = [
        [InlineKeyboardButton("🎲 Manage Actions", callback_data="manage_action")],
        [InlineKeyboardButton("👤 Manage Subjects", callback_data="manage_subject")],
        [InlineKeyboardButton("🔙 Back to Groups", callback_data="back_to_groups")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text("What would you like to configure for this group?", reply_markup=reply_markup)
    return SELECT_CATEGORY

async def category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "back_to_groups":
        return await _show_groups(query)
        
    face_type = query.data.split('_')[1] # 'action' or 'subject'
    context.user_data['settings_face_type'] = face_type
    group_id = context.user_data['settings_group_id']
    
    group = await database.get_or_create_group(group_id)
    if not group.get('is_premium'):
        await query.edit_message_text("This group is on the free tier! 🌟 Premium is required to customize Actions and Subjects. Run /upgrade in your group chat to unlock.")
        return ConversationHandler.END
    
    faces = await database.get_dice_faces(group_id, face_type)
    
    keyboard = []
    for face in faces:
        keyboard.append([InlineKeyboardButton(f"❌ {face}", callback_data=f"delete_{face}")])
        
    keyboard.append([InlineKeyboardButton("➕ Add New", callback_data="add_new")])
    keyboard.append([InlineKeyboardButton("📤 Export List", callback_data="export_list"), InlineKeyboardButton("📥 Bulk Import", callback_data="bulk_import")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Category", callback_data="back_to_category")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"Managing {face_type}s. Click ❌ to delete, or Add New:", reply_markup=reply_markup)
    return MANAGE_ITEMS

async def _show_groups(query):
    groups = await database.get_groups_by_owner(query.from_user.id)
    keyboard = []
    for g in groups:
        keyboard.append([InlineKeyboardButton(g['group_title'] or f"Group {g['group_id']}", callback_data=f"group_{g['group_id']}")])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Please select a group you own to configure:", reply_markup=reply_markup)
    return SELECT_GROUP

async def manage_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "back_to_category":
        keyboard = [
            [InlineKeyboardButton("🎲 Manage Actions", callback_data="manage_action")],
            [InlineKeyboardButton("👤 Manage Subjects", callback_data="manage_subject")],
            [InlineKeyboardButton("🔙 Back to Groups", callback_data="back_to_groups")]
        ]
        await query.edit_message_text("What would you like to configure for this group?", reply_markup=InlineKeyboardMarkup(keyboard))
        return SELECT_CATEGORY
        
    if query.data == "add_new":
        await query.edit_message_text("Please type the new value you want to add. (Or type /cancel to abort)")
        return WAITING_FOR_INPUT
        
    if query.data == "export_list":
        group_id = context.user_data['settings_group_id']
        face_type = context.user_data['settings_face_type']
        faces = await database.get_dice_faces(group_id, face_type)
        text_list = "\n".join(faces) if faces else "List is empty."
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text=f"Here are all your current {face_type}s. You can copy this text, edit it, and use Bulk Import to load them back:\n\n{text_list}"
        )
        return MANAGE_ITEMS
        
    if query.data == "bulk_import":
        await query.edit_message_text("Please reply with your list of items (one per line). I will add them all at once! (Or type /cancel to abort)")
        return WAITING_FOR_BULK_INPUT
        
    if query.data.startswith("delete_"):
        value = query.data[len("delete_"):]
        group_id = context.user_data['settings_group_id']
        face_type = context.user_data['settings_face_type']
        await database.remove_dice_face(group_id, face_type, value)
        
        # Refresh the list
        faces = await database.get_dice_faces(group_id, face_type)
        keyboard = []
        for face in faces:
            keyboard.append([InlineKeyboardButton(f"❌ {face}", callback_data=f"delete_{face}")])
        keyboard.append([InlineKeyboardButton("➕ Add New", callback_data="add_new")])
        keyboard.append([InlineKeyboardButton("📤 Export List", callback_data="export_list"), InlineKeyboardButton("📥 Bulk Import", callback_data="bulk_import")])
        keyboard.append([InlineKeyboardButton("🔙 Back to Category", callback_data="back_to_category")])
        
        await query.edit_message_text(f"Deleted '{value}'. Managing {face_type}s:", reply_markup=InlineKeyboardMarkup(keyboard))
        return MANAGE_ITEMS

async def input_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = update.message.text
    group_id = context.user_data['settings_group_id']
    face_type = context.user_data['settings_face_type']
    
    success = await database.add_dice_face(group_id, face_type, value)
    
    faces = await database.get_dice_faces(group_id, face_type)
    keyboard = []
    for face in faces:
        keyboard.append([InlineKeyboardButton(f"❌ {face}", callback_data=f"delete_{face}")])
    keyboard.append([InlineKeyboardButton("➕ Add New", callback_data="add_new")])
    keyboard.append([InlineKeyboardButton("📤 Export List", callback_data="export_list"), InlineKeyboardButton("📥 Bulk Import", callback_data="bulk_import")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Category", callback_data="back_to_category")])
    
    msg = f"✅ Added '{value}'!" if success else f"❌ '{value}' already exists."
    await update.message.reply_text(f"{msg}\n\nManaging {face_type}s:", reply_markup=InlineKeyboardMarkup(keyboard))
    return MANAGE_ITEMS

async def bulk_input_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    group_id = context.user_data['settings_group_id']
    face_type = context.user_data['settings_face_type']
    
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    added = 0
    skipped = 0
    
    for line in lines:
        success = await database.add_dice_face(group_id, face_type, line)
        if success:
            added += 1
        else:
            skipped += 1
            
    faces = await database.get_dice_faces(group_id, face_type)
    keyboard = []
    for face in faces:
        keyboard.append([InlineKeyboardButton(f"❌ {face}", callback_data=f"delete_{face}")])
    keyboard.append([InlineKeyboardButton("➕ Add New", callback_data="add_new")])
    keyboard.append([InlineKeyboardButton("📤 Export List", callback_data="export_list"), InlineKeyboardButton("📥 Bulk Import", callback_data="bulk_import")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Category", callback_data="back_to_category")])
    
    msg = f"✅ Added {added} new items. ({skipped} skipped/already existed)."
    await update.message.reply_text(f"{msg}\n\nManaging {face_type}s:", reply_markup=InlineKeyboardMarkup(keyboard))
    return MANAGE_ITEMS

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Settings configuration cancelled.")
    return ConversationHandler.END

def get_settings_handler():
    return ConversationHandler(
        entry_points=[CommandHandler('settings', settings_command)],
        states={
            SELECT_GROUP: [CallbackQueryHandler(group_selected)],
            SELECT_CATEGORY: [CallbackQueryHandler(category_selected)],
            MANAGE_ITEMS: [CallbackQueryHandler(manage_items)],
            WAITING_FOR_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_received)],
            WAITING_FOR_BULK_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bulk_input_received)]
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True
    )
