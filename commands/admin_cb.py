from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode
import asyncio
from database import *
from helper_func import check_admin, format_time
from admin_state import admin_conversations, set_admin_conversation, clear_admin_conversation

# Store conversation states
admin_conversations = {}

# ==================== ADMIN FILES COMMAND ====================

@Client.on_message(filters.command("files") & filters.private)
async def files_admin_command(client: Client, message: Message):
    """Admin command to manage file settings"""
    try:
        # Check admin
        if not check_admin(client, message.from_user, message):
            await message.reply_text("❌ ᴜɴᴀᴜᴛʜᴏʀɪᴢᴇᴅ", parse_mode=ParseMode.HTML)
            return
            
        settings = await get_file_settings()
        settings_text = create_files_settings_text(settings)
        keyboard = create_files_admin_keyboard(settings)
        
        await message.reply_text(
            settings_text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
        
    except Exception as e:
        print(f"❌ Error in files admin command: {e}")
        await message.reply_text(
            f"<b>❌ ᴇʀʀᴏʀ:</b> <code>{str(e)}</code>",
            parse_mode=ParseMode.HTML
        )

def create_files_settings_text(settings):
    """Create settings display text"""
    protect_status = "🔒 ᴇɴᴀʙʟᴇᴅ" if settings.get('protect_content', False) else "🔓 ᴅɪsᴀʙʟᴇᴅ"
    caption_status = "👁️ sʜᴏᴡ" if settings.get('show_caption', True) else "🙈 ʜɪᴅᴇ"
    auto_del_status = "⏰ ᴇɴᴀʙʟᴇᴅ" if settings.get('auto_delete', False) else "♾️ ᴅɪsᴀʙʟᴇᴅ"
    inline_btn_status = "🔘 ᴇɴᴀʙʟᴇᴅ" if settings.get('inline_buttons', True) else "⚪ ᴅɪsᴀʙʟᴇᴅ"
    spoiler_status = "🙈 ᴇɴᴀʙʟᴇᴅ" if settings.get('spoiler_enabled', False) else "👁️ ᴅɪsᴀʙʟᴇᴅ"
    
    auto_del_time = settings.get('auto_delete_time', 300)
    button_name = settings.get('button_name', '📺 ᴍᴏʀᴇ ᴠɪᴅᴇᴏs')
    button_url = settings.get('button_url', 'https://t.me/shizukawachan')
    
    text = f"""<b>📁 ғɪʟᴇ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ sᴇᴛᴛɪɴɢs</b>

<b>🔒 ᴘʀᴏᴛᴇᴄᴛ ᴄᴏɴᴛᴇɴᴛ:</b> {protect_status}
<i>• ᴅɪsᴀʙʟᴇs ғᴏʀᴡᴀʀᴅɪɴɢ ᴀɴᴅ sᴀᴠɪɴɢ</i>

<b>👁️ sʜᴏᴡ ᴄᴀᴘᴛɪᴏɴ:</b> {caption_status}
<i>• sʜᴏᴡ/ʜɪᴅᴇ ᴄᴀᴘᴛɪᴏɴ ᴏɴ ғɪʟᴇs</i>

<b>⏰ ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ:</b> {auto_del_status}
<i>• ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ ᴀғᴛᴇʀ: {format_time(auto_del_time)}</i>

<b>🔘 ɪɴʟɪɴᴇ ʙᴜᴛᴛᴏɴs:</b> {inline_btn_status}
<i>• sʜᴏᴡ/ʜɪᴅᴇ ɪɴʟɪɴᴇ ʙᴜᴛᴛᴏɴs</i>

<b>🔗 ʙᴜᴛᴛᴏɴ ɴᴀᴍᴇ:</b> <code>{button_name}</code>
<b>🌐 ʙᴜᴛᴛᴏɴ ᴜʀʟ:</b> <code>{button_url}</code>

<i>💡 ᴄʟɪᴄᴋ ʙᴜᴛᴛᴏɴs ʙᴇʟᴏᴡ ᴛᴏ ᴄʜᴀɴɢᴇ sᴇᴛᴛɪɴɢs</i>"""
    
    return text

def create_files_admin_keyboard(settings):
    """Create admin keyboard for file settings"""
    protect_text = "🔓 ᴅɪsᴀʙʟᴇ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ" if settings.get('protect_content', False) else "🔒 ᴇɴᴀʙʟᴇ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ"
    caption_text = "🙈 ʜɪᴅᴇ ᴄᴀᴘᴛɪᴏɴ" if settings.get('show_caption', True) else "👁️ sʜᴏᴡ ᴄᴀᴘᴛɪᴏɴ"
    spoiler_text = "👁️ ᴅɪsᴀʙʟᴇ sᴘᴏɪʟᴇʀ" if settings.get('spoiler_enabled', False) else "🙈 ᴇɴᴀʙʟᴇ sᴘᴏɪʟᴇʀ"
    auto_del_text = "♾️ ᴅɪsᴀʙʟᴇ ᴀᴜᴛᴏ ᴅᴇʟ" if settings.get('auto_delete', False) else "⏰ ᴇɴᴀʙʟᴇ ᴀᴜᴛᴏ ᴅᴇʟ"
    inline_text = "⚪ ᴅɪsᴀʙʟᴇ ʙᴜᴛᴛᴏɴs" if settings.get('inline_buttons', True) else "🔘 ᴇɴᴀʙʟᴇ ʙᴜᴛᴛᴏɴs"
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(protect_text, callback_data="files_toggle_protect"),
            InlineKeyboardButton(caption_text, callback_data="files_toggle_caption")
        ],
        [
            InlineKeyboardButton(spoiler_text, callback_data="files_toggle_spoiler"),
            InlineKeyboardButton(auto_del_text, callback_data="files_toggle_autodel")
        ],
        [
            InlineKeyboardButton(inline_text, callback_data="files_toggle_buttons"),
            InlineKeyboardButton("⏱️ sᴇᴛ ᴀᴜᴛᴏ ᴅᴇʟ ᴛɪᴍᴇ", callback_data="files_set_time")
        ],
        [
            InlineKeyboardButton("🔗 sᴇᴛ ʙᴜᴛᴛᴏɴ ɴᴀᴍᴇ", callback_data="files_set_btn_name"),
            InlineKeyboardButton("🌐 sᴇᴛ ʙᴜᴛᴛᴏɴ ᴜʀʟ", callback_data="files_set_btn_url")
        ],
        [
            InlineKeyboardButton("🔄 ʀᴇғʀᴇsʜ", callback_data="files_refresh"),
            InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="files_close")
        ]
    ])
    
    return keyboard

# ==================== CALLBACK HANDLERS ====================

@Client.on_callback_query(filters.regex("^files_"))
async def files_callback_handler(client: Client, callback_query: CallbackQuery):
    """Handle file settings callbacks"""
    try:
        data = callback_query.data
        user_id = callback_query.from_user.id
        
        if not check_admin(client, callback_query.from_user, callback_query.message):
            await callback_query.answer("❌ ᴜɴᴀᴜᴛʜᴏʀɪᴢᴇᴅ", show_alert=True)
            return
        
        if data == "files_toggle_protect":
            await toggle_protect_content(client, callback_query)
        elif data == "files_toggle_caption":
            await toggle_show_caption(client, callback_query)
        elif data == "files_toggle_spoiler":
            await toggle_spoiler_mode(client, callback_query)
        elif data == "files_toggle_autodel":
            await toggle_auto_delete(client, callback_query)
        elif data == "files_toggle_buttons":
            await toggle_inline_buttons(client, callback_query)
        elif data == "files_set_time":
            await set_auto_delete_time(client, callback_query)
        elif data == "files_set_btn_name":
            await set_button_name(client, callback_query)
        elif data == "files_set_btn_url":
            await set_button_url(client, callback_query)
        elif data == "files_refresh":
            await refresh_files_settings(client, callback_query)
        elif data == "files_close":
            await callback_query.message.delete()
            await callback_query.answer("✅ ᴄʟᴏsᴇᴅ")
        
    except Exception as e:
        print(f"❌ Error in files callback: {e}")
        await callback_query.answer(f"❌ ᴇʀʀᴏʀ: {str(e)}", show_alert=True)

# ==================== TOGGLE FUNCTIONS ====================

async def toggle_spoiler_mode(client: Client, callback_query: CallbackQuery):
    """Toggle spoiler mode setting"""
    try:
        current_settings = await get_file_settings()
        new_value = not current_settings.get('spoiler_enabled', False)
        
        await update_file_setting('spoiler_enabled', new_value)
        
        status = "ᴇɴᴀʙʟᴇᴅ" if new_value else "ᴅɪsᴀʙʟᴇᴅ"
        await callback_query.answer(f"🙈 sᴘᴏɪʟᴇʀ ᴍᴏᴅᴇ {status}")
        
        await refresh_files_settings(client, callback_query, show_answer=False)
        
    except Exception as e:
        await callback_query.answer(f"❌ ᴇʀʀᴏʀ: {str(e)}", show_alert=True)
        
async def toggle_protect_content(client: Client, callback_query: CallbackQuery):
    """Toggle protect content setting"""
    try:
        current_settings = await get_file_settings()
        new_value = not current_settings.get('protect_content', False)
        
        await update_file_setting('protect_content', new_value)
        
        status = "ᴇɴᴀʙʟᴇᴅ" if new_value else "ᴅɪsᴀʙʟᴇᴅ"
        await callback_query.answer(f"🔒 ᴘʀᴏᴛᴇᴄᴛ ᴄᴏɴᴛᴇɴᴛ {status}")
        
        await refresh_files_settings(client, callback_query, show_answer=False)
        
    except Exception as e:
        await callback_query.answer(f"❌ ᴇʀʀᴏʀ: {str(e)}", show_alert=True)

async def toggle_show_caption(client: Client, callback_query: CallbackQuery):
    """Toggle show caption setting"""
    try:
        current_settings = await get_file_settings()
        new_value = not current_settings.get('show_caption', True)
        
        await update_file_setting('show_caption', new_value)
        
        status = "sʜᴏᴡ" if new_value else "ʜɪᴅᴇ"
        await callback_query.answer(f"👁️ ᴄᴀᴘᴛɪᴏɴ sᴇᴛ ᴛᴏ {status}")
        
        await refresh_files_settings(client, callback_query, show_answer=False)
        
    except Exception as e:
        await callback_query.answer(f"❌ ᴇʀʀᴏʀ: {str(e)}", show_alert=True)

async def toggle_auto_delete(client: Client, callback_query: CallbackQuery):
    """Toggle auto delete setting"""
    try:
        current_settings = await get_file_settings()
        new_value = not current_settings.get('auto_delete', False)
        
        await update_file_setting('auto_delete', new_value)
        
        status = "ᴇɴᴀʙʟᴇᴅ" if new_value else "ᴅɪsᴀʙʟᴇᴅ"
        await callback_query.answer(f"⏰ ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ {status}")
        
        await refresh_files_settings(client, callback_query, show_answer=False)
        
    except Exception as e:
        await callback_query.answer(f"❌ ᴇʀʀᴏʀ: {str(e)}", show_alert=True)

async def toggle_inline_buttons(client: Client, callback_query: CallbackQuery):
    """Toggle inline buttons setting"""
    try:
        current_settings = await get_file_settings()
        new_value = not current_settings.get('inline_buttons', True)
        
        await update_file_setting('inline_buttons', new_value)
        
        status = "ᴇɴᴀʙʟᴇᴅ" if new_value else "ᴅɪsᴀʙʟᴇᴅ"
        await callback_query.answer(f"🔘 ɪɴʟɪɴᴇ ʙᴜᴛᴛᴏɴs {status}")
        
        await refresh_files_settings(client, callback_query, show_answer=False)
        
    except Exception as e:
        await callback_query.answer(f"❌ ᴇʀʀᴏʀ: {str(e)}", show_alert=True)

# ==================== CONVERSATION HANDLERS ====================

async def set_auto_delete_time(client: Client, callback_query: CallbackQuery):
    """Set auto delete time using conversation"""
    try:
        user_id = callback_query.from_user.id
        
        # Store conversation state
        admin_conversations[user_id] = {
            'state': 'waiting_auto_delete_time',
            'message_id': callback_query.message.id,
            'chat_id': callback_query.message.chat.id,
            'timestamp': asyncio.get_event_loop().time()
        }
        
        await callback_query.answer()
        
        # Send instruction message
        instruction_msg = await callback_query.message.reply_text(
            "<b>⏱️ sᴇᴛ ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ ᴛɪᴍᴇ</b>\n\n"
            "ᴘʟᴇᴀsᴇ sᴇɴᴅ ᴛɪᴍᴇ ɪɴ sᴇᴄᴏɴᴅs:\n"
            "• <code>300</code> = 5 ᴍɪɴᴜᴛᴇs\n"
            "• <code>600</code> = 10 ᴍɪɴᴜᴛᴇs\n"
            "• <code>1800</code> = 30 ᴍɪɴᴜᴛᴇs\n\n"
            "<i>⏰ ʏᴏᴜ ʜᴀᴠᴇ 2 ᴍɪɴᴜᴛᴇs ᴛᴏ ʀᴇsᴘᴏɴᴅ</i>\n"
            "<i>💡 sᴇɴᴅ /cancel ᴛᴏ ᴄᴀɴᴄᴇʟ</i>",
            parse_mode=ParseMode.HTML
        )
        
        # Store instruction message ID for cleanup
        admin_conversations[user_id]['instruction_msg_id'] = instruction_msg.id
        
        # Set timeout
        asyncio.create_task(conversation_timeout(user_id, 120))  # 2 minutes
        
    except Exception as e:
        print(f"❌ Error setting auto delete time: {e}")
        await callback_query.answer(f"❌ ᴇʀʀᴏʀ: {str(e)}", show_alert=True)

async def set_button_name(client: Client, callback_query: CallbackQuery):
    """Set button name using conversation"""
    try:
        user_id = callback_query.from_user.id
        
        admin_conversations[user_id] = {
            'state': 'waiting_button_name',
            'message_id': callback_query.message.id,
            'chat_id': callback_query.message.chat.id,
            'timestamp': asyncio.get_event_loop().time()
        }
        
        await callback_query.answer()
        
        instruction_msg = await callback_query.message.reply_text(
            "<b>🔗 sᴇᴛ ʙᴜᴛᴛᴏɴ ɴᴀᴍᴇ</b>\n\n"
            "ᴘʟᴇᴀsᴇ sᴇɴᴅ ɴᴇᴡ ʙᴜᴛᴛᴏɴ ɴᴀᴍᴇ:\n"
            "• <code>📺 ᴍᴏʀᴇ ᴠɪᴅᴇᴏs</code>\n"
            "• <code>🎬 ᴡᴀᴛᴄʜ ᴍᴏʀᴇ</code>\n"
            "• <code>📢 ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ</code>\n\n"
            "<i>⏰ ʏᴏᴜ ʜᴀᴠᴇ 2 ᴍɪɴᴜᴛᴇs ᴛᴏ ʀᴇsᴘᴏɴᴅ</i>\n"
            "<i>💡 sᴇɴᴅ /cancel ᴛᴏ ᴄᴀɴᴄᴇʟ</i>",
            parse_mode=ParseMode.HTML
        )
        
        admin_conversations[user_id]['instruction_msg_id'] = instruction_msg.id
        asyncio.create_task(conversation_timeout(user_id, 120))
        
    except Exception as e:
        print(f"❌ Error setting button name: {e}")
        await callback_query.answer(f"❌ ᴇʀʀᴏʀ: {str(e)}", show_alert=True)

async def set_button_url(client: Client, callback_query: CallbackQuery):
    """Set button URL using conversation"""
    try:
        user_id = callback_query.from_user.id
        
        print(f"🔧 Setting button URL conversation for user {user_id}")
        
        # Set conversation state
        conversation_data = {
            'state': 'waiting_button_url',
            'message_id': callback_query.message.id,
            'chat_id': callback_query.message.chat.id,
            'timestamp': asyncio.get_event_loop().time()
        }
        
        # Use the imported function to set conversation
        set_admin_conversation(user_id, conversation_data)
        
        # Also set directly in the global dict as backup
        admin_conversations[user_id] = conversation_data
        
        print(f"✅ Admin conversation state set for user {user_id}: {admin_conversations.get(user_id)}")
        print(f"📊 Current admin_conversations: {list(admin_conversations.keys())}")
        
        await callback_query.answer()
        
        instruction_msg = await callback_query.message.reply_text(
            "<b>🌐 sᴇᴛ ʙᴜᴛᴛᴏɴ ᴜʀʟ</b>\n\n"
            "ᴘʟᴇᴀsᴇ sᴇɴᴅ ɴᴇᴡ ʙᴜᴛᴛᴏɴ ᴜʀʟ:\n"
            "• <code>https://t.me/yourchannel</code>\n"
            "• <code>t.me/yourchannel</code>\n"
            "• <code>https://example.com</code>\n\n"
            "<i>⏰ ʏᴏᴜ ʜᴀᴠᴇ 2 ᴍɪɴᴜᴛᴇs ᴛᴏ ʀᴇsᴘᴏɴᴅ</i>\n"
            "<i>💡 sᴇɴᴅ /cancel ᴛᴏ ᴄᴀɴᴄᴇʟ</i>",
            parse_mode=ParseMode.HTML
        )
        
        # Update conversation with instruction message ID
        admin_conversations[user_id]['instruction_msg_id'] = instruction_msg.id
        
        print(f"📝 Instruction message sent with ID: {instruction_msg.id}")
        
        asyncio.create_task(conversation_timeout(user_id, 120))
        
    except Exception as e:
        print(f"❌ Error setting button URL conversation: {e}")
        await callback_query.answer(f"❌ ᴇʀʀᴏʀ: {str(e)}", show_alert=True)


async def refresh_files_settings(client: Client, callback_query: CallbackQuery, show_answer=True):
    """Refresh the files settings display"""
    try:
        settings = await get_file_settings()
        settings_text = create_files_settings_text(settings)
        keyboard = create_files_admin_keyboard(settings)
        
        await callback_query.message.edit_text(
            settings_text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
        
        if show_answer:
            await callback_query.answer("🔄 ʀᴇғʀᴇsʜᴇᴅ")
        
    except Exception as e:
        await callback_query.answer(f"❌ ᴇʀʀᴏʀ: {str(e)}", show_alert=True)

# ==================== CONVERSATION MESSAGE HANDLER ====================

@Client.on_message(filters.private & filters.text)
async def handle_admin_conversation_logic(client: Client, message: Message):
    """Handle admin conversation logic - can be called from anywhere"""
    try:
        user_id = message.from_user.id
        
        print(f"🎯 Admin conversation logic called for user {user_id}")
        
        if user_id not in admin_conversations:
            print(f"❌ User {user_id} not in admin conversations")
            return
        
        # Check if user is admin
        if not check_admin(client, message.from_user, message):
            print(f"❌ User {user_id} not admin but in conversation - clearing state")
            clear_admin_conversation(user_id)
            return
        
        conversation = admin_conversations[user_id]
        state = conversation['state']
        
        print(f"📝 Processing admin conversation state: {state}")
        
        # Handle cancel command
        if message.text.strip().lower() in ['/cancel', 'cancel']:
            await cancel_conversation(client, message, user_id)
            return
        
        # Handle different conversation states
        if state == 'waiting_auto_delete_time':
            await handle_auto_delete_time_input(client, message, user_id)
        elif state == 'waiting_button_name':
            await handle_button_name_input(client, message, user_id)
        elif state == 'waiting_button_url':
            await handle_button_url_input(client, message, user_id)
        
        print(f"✅ Admin conversation processed successfully")
        
    except Exception as e:
        print(f"❌ Error in admin conversation logic: {e}")
        import traceback
        traceback.print_exc()


async def handle_auto_delete_time_input(client: Client, message: Message, user_id: int):
    """Handle auto delete time input"""
    try:
        conversation = admin_conversations[user_id]
        time_text = message.text.strip()
        
        # Validate input
        try:
            time_seconds = int(time_text)
            if time_seconds < 60:
                await message.reply_text(
                    "<b>❌ ɪɴᴠᴀʟɪᴅ ᴛɪᴍᴇ</b>\n\n"
                    "ᴍɪɴɪᴍᴜᴍ ᴛɪᴍᴇ ɪs 60 sᴇᴄᴏɴᴅs (1 ᴍɪɴᴜᴛᴇ)\n"
                    "<i>ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ ᴏʀ sᴇɴᴅ /cancel</i>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            if time_seconds > 86400:
                await message.reply_text(
                    "<b>❌ ɪɴᴠᴀʟɪᴅ ᴛɪᴍᴇ</b>\n\n"
                    "ᴍᴀxɪᴍᴜᴍ ᴛɪᴍᴇ ɪs 86400 sᴇᴄᴏɴᴅs (24 ʜᴏᴜʀs)\n"
                    "<i>ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ ᴏʀ sᴇɴᴅ /cancel</i>",
                    parse_mode=ParseMode.HTML
                )
                return
                
        except ValueError:
            await message.reply_text(
                "<b>❌ ɪɴᴠᴀʟɪᴅ ɪɴᴘᴜᴛ</b>\n\n"
                "ᴘʟᴇᴀsᴇ sᴇɴᴅ ᴀ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ ɪɴ sᴇᴄᴏɴᴅs\n"
                "<i>ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ ᴏʀ sᴇɴᴅ /cancel</i>",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Update setting
        await update_file_setting('auto_delete_time', time_seconds)
        
        # Update settings message
        await update_settings_message(client, conversation['chat_id'], conversation['message_id'])
        
        # Clean up conversation
        await cleanup_conversation(client, user_id, message)
        
        # Send success message
        success_msg = await message.reply_text(
            f"<b>✅ ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ ᴛɪᴍᴇ ᴜᴘᴅᴀᴛᴇᴅ!</b>\n\n"
            f"<b>⏰ ɴᴇᴡ ᴛɪᴍᴇ:</b> {format_time(time_seconds)}",
            parse_mode=ParseMode.HTML
        )
        
        # Auto delete success message
        asyncio.create_task(delete_message_after_delay(client, success_msg.chat.id, success_msg.id, 5))
        
    except Exception as e:
        print(f"❌ Error handling auto delete time input: {e}")

async def handle_button_name_input(client: Client, message: Message, user_id: int):
    """Handle button name input"""
    try:
        conversation = admin_conversations[user_id]
        button_name = message.text.strip()
        
        # Validate input
        if len(button_name) < 1:
            await message.reply_text(
                "<b>❌ ɪɴᴠᴀʟɪᴅ ɴᴀᴍᴇ</b>\n\n"
                "ʙᴜᴛᴛᴏɴ ɴᴀᴍᴇ ᴄᴀɴɴᴏᴛ ʙᴇ ᴇᴍᴘᴛʏ\n"
                "<i>ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ ᴏʀ sᴇɴᴅ /cancel</i>",
                parse_mode=ParseMode.HTML
            )
            return
        
        if len(button_name) > 50:
            await message.reply_text(
                "<b>❌ ɴᴀᴍᴇ ᴛᴏᴏ ʟᴏɴɢ</b>\n\n"
                "ʙᴜᴛᴛᴏɴ ɴᴀᴍᴇ ᴍᴜsᴛ ʙᴇ ᴜɴᴅᴇʀ 50 ᴄʜᴀʀᴀᴄᴛᴇʀs\n"
                "<i>ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ ᴏʀ sᴇɴᴅ /cancel</i>",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Update setting
        await update_file_setting('button_name', button_name)
        
        # Update settings message
        await update_settings_message(client, conversation['chat_id'], conversation['message_id'])
        
        # Clean up conversation
        await cleanup_conversation(client, user_id, message)
        
        # Send success message
        success_msg = await message.reply_text(
            f"<b>✅ ʙᴜᴛᴛᴏɴ ɴᴀᴍᴇ ᴜᴘᴅᴀᴛᴇᴅ!</b>\n\n"
            f"<b>🔗 ɴᴇᴡ ɴᴀᴍᴇ:</b> <code>{button_name}</code>",
            parse_mode=ParseMode.HTML
        )
        
        asyncio.create_task(delete_message_after_delay(client, success_msg.chat.id, success_msg.id, 5))
        
    except Exception as e:
        print(f"❌ Error handling button name input: {e}")

async def handle_button_url_input(client: Client, message: Message, user_id: int):
    """Handle button URL input"""
    try:
        print(f"🌐 Starting button URL input handling for user {user_id}")
        
        conversation = admin_conversations[user_id]
        url_text = message.text.strip()
        
        print(f"📝 Received URL text: {url_text}")
        
        # Basic URL validation
        if not url_text.startswith(('http://', 'https://', 't.me/')):
            print(f"❌ Invalid URL format: {url_text}")
            await message.reply_text(
                "<b>❌ ɪɴᴠᴀʟɪᴅ ᴜʀʟ</b>\n\n"
                "ᴘʟᴇᴀsᴇ sᴇɴᴅ ᴀ ᴠᴀʟɪᴅ ᴜʀʟ sᴛᴀʀᴛɪɴɢ ᴡɪᴛʜ:\n"
                "• https://t.me/channel\n"
                "• t.me/channel\n"
                "• https://example.com\n\n"
                "<i>ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ ᴏʀ sᴇɴᴅ /cancel</i>",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Normalize URL
        if url_text.startswith('t.me/'):
            url_text = 'https://' + url_text
        
        print(f"🔧 Normalized URL: {url_text}")
        
        # Update setting in database
        print(f"💾 Updating database with button_url: {url_text}")
        try:
            await update_file_setting('button_url', url_text)
            print(f"✅ Database updated successfully")
        except Exception as db_error:
            print(f"❌ Database update failed: {db_error}")
            await message.reply_text(
                f"<b>❌ ᴅᴀᴛᴀʙᴀsᴇ ᴇʀʀᴏʀ</b>\n\n"
                f"<code>{str(db_error)}</code>\n\n"
                "<i>ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ ᴏʀ sᴇɴᴅ /cancel</i>",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Update settings message
        print(f"🔄 Updating settings message")
        try:
            await update_settings_message(client, conversation['chat_id'], conversation['message_id'])
            print(f"✅ Settings message updated successfully")
        except Exception as update_error:
            print(f"❌ Settings message update failed: {update_error}")
        
        # Clean up conversation
        print(f"🧹 Cleaning up conversation")
        await cleanup_conversation(client, user_id, message)
        
        # Send success message
        print(f"📤 Sending success message")
        success_msg = await message.reply_text(
            f"<b>✅ ʙᴜᴛᴛᴏɴ ᴜʀʟ ᴜᴘᴅᴀᴛᴇᴅ!</b>\n\n"
            f"<b>🌐 ɴᴇᴡ ᴜʀʟ:</b> <code>{url_text}</code>",
            parse_mode=ParseMode.HTML
        )
        
        # Verify the update by checking database
        print(f"🔍 Verifying database update...")
        try:
            current_settings = await get_file_settings()
            stored_url = current_settings.get('button_url', 'NOT_FOUND')
            print(f"📊 Current button_url in database: {stored_url}")
            
            if stored_url == url_text:
                print(f"✅ Database verification successful - URL matches")
            else:
                print(f"❌ Database verification failed - URL mismatch!")
                print(f"   Expected: {url_text}")
                print(f"   Got: {stored_url}")
        except Exception as verify_error:
            print(f"❌ Database verification failed: {verify_error}")
        
        asyncio.create_task(delete_message_after_delay(client, success_msg.chat.id, success_msg.id, 5))
        
        print(f"✅ Button URL input handling completed for user {user_id}")
        
    except Exception as e:
        print(f"❌ Error handling button URL input: {e}")
        import traceback
        traceback.print_exc()
        
        # Send error message to user
        try:
            await message.reply_text(
                f"<b>❌ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ</b>\n\n"
                f"<code>{str(e)}</code>\n\n"
                "<i>ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ ᴏʀ sᴇɴᴅ /cancel</i>",
                parse_mode=ParseMode.HTML
            )
        except:
            pass


# ==================== CONVERSATION HELPER FUNCTIONS ====================

async def cancel_conversation(client: Client, message: Message, user_id: int):
    """Cancel active conversation"""
    try:
        if user_id in admin_conversations:
            await cleanup_conversation(client, user_id, message)
            
            cancel_msg = await message.reply_text(
                "<b>❌ ᴄᴀɴᴄᴇʟʟᴇᴅ</b>\n\n"
                "ᴏᴘᴇʀᴀᴛɪᴏɴ ᴄᴀɴᴄᴇʟʟᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ",
                parse_mode=ParseMode.HTML
            )
            
            asyncio.create_task(delete_message_after_delay(client, cancel_msg.chat.id, cancel_msg.id, 3))
            
    except Exception as e:
        print(f"❌ Error cancelling conversation: {e}")

async def cleanup_conversation(client: Client, user_id: int, user_message: Message):
    """Clean up conversation state and messages"""
    try:
        if user_id in admin_conversations:
            conversation = admin_conversations[user_id]
            
            # Delete instruction message
            if 'instruction_msg_id' in conversation:
                try:
                    await client.delete_messages(
                        chat_id=conversation['chat_id'],
                        message_ids=conversation['instruction_msg_id']
                    )
                except Exception:
                    pass
            
            # Delete user's input message
            try:
                await user_message.delete()
            except Exception:
                pass
            
            # Remove conversation state
            del admin_conversations[user_id]
            
    except Exception as e:
        print(f"❌ Error cleaning up conversation: {e}")

async def conversation_timeout(user_id: int, timeout_seconds: int):
    """Handle conversation timeout"""
    try:
        await asyncio.sleep(timeout_seconds)
        
        if user_id in admin_conversations:
            conversation = admin_conversations[user_id]
            
            # Check if conversation is still active (not processed)
            current_time = asyncio.get_event_loop().time()
            if current_time - conversation['timestamp'] >= timeout_seconds:
                # Send timeout message
                try:
                    from pyrogram import Client
                    # Note: We need client instance here, but it's not directly available
                    # This is a limitation of this approach
                    print(f"⏰ Conversation timeout for user {user_id}")
                    
                    # Clean up conversation
                    del admin_conversations[user_id]
                    
                except Exception as e:
                    print(f"❌ Error in conversation timeout: {e}")
                    
    except Exception as e:
        print(f"❌ Error in conversation timeout handler: {e}")

async def update_settings_message(client: Client, chat_id: int, message_id: int):
    """Update the settings message with new data"""
    try:
        settings = await get_file_settings()
        settings_text = create_files_settings_text(settings)
        keyboard = create_files_admin_keyboard(settings)
        
        await client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=settings_text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
        print("✅ Settings message updated successfully")
        
    except Exception as e:
        print(f"❌ Error updating settings message: {e}")

async def delete_message_after_delay(client: Client, chat_id: int, message_id: int, delay: int):
    """Delete message after specified delay"""
    try:
        await asyncio.sleep(delay)
        await client.delete_messages(chat_id, message_id)
    except Exception as e:
        print(f"❌ Error deleting message after delay: {e}")

print("✅ Admin callback handlers with conversation system loaded successfully")
