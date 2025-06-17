from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ChatJoinRequest
from pyrogram.errors import UserNotParticipant
from pyrogram.enums import ParseMode
from config import Config
import os
from database import *
from datetime import datetime

OWNER_ID = int(os.environ.get("OWNER_ID", "7560922302"))
OWNER_TAG = os.environ.get("OWNER_TAG", "shizukawachan")
ADMIN_LIST = os.environ.get("ADMINS", "").split()
ADMINS = [int(admin) for admin in ADMIN_LIST if admin.isdigit()]
ADMINS.append(OWNER_ID)
FORCE_PIC = os.environ.get("FORCE_PIC", "https://ibb.co/WNSk3Q6x")

async def check_subscription(client: Client, message: Message) -> bool:
    """Check if user is subscribed to required channels"""
    try:
        settings = await get_settings()
        FORCE_SUB_CHANNELS = settings.get("FORCE_SUB_CHANNELS", [])
        REQUEST_SUB_CHANNELS = settings.get("REQUEST_SUB_CHANNELS", [])
        user_id = message.from_user.id
        
        # Skip checks for admins
        if user_id in ADMINS:
            return True
        
        # If no channels configured, allow access
        if not FORCE_SUB_CHANNELS and not REQUEST_SUB_CHANNELS:
            return True
            
        # Initialize variables to track which channels the user needs to join
        force_channels_to_join = []
        request_channels_to_join = []
        
        # Check force sub channels
        for channel in FORCE_SUB_CHANNELS:
            try:
                member = await client.get_chat_member(channel, user_id)
                if member.status not in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.MEMBER]:
                    force_channels_to_join.append(channel)
            except UserNotParticipant:
                force_channels_to_join.append(channel)
            except Exception as e:
                force_channels_to_join.append(channel)
                
        # Check request channels
        for channel in REQUEST_SUB_CHANNELS:
            try:
                # Convert channel to int for comparison
                channel_id = int(channel) if isinstance(channel, str) and channel.lstrip('-').isdigit() else channel
                
                # First check if user is already a member
                try:
                    member = await client.get_chat_member(channel, user_id)
                    if member.status in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.MEMBER]:
                        # Remove any pending request since user is now a member
                        await remove_join_request(user_id, channel_id)
                        continue
                except UserNotParticipant:
                    pass
                
                # Check if user has a pending request
                if await has_pending_request(user_id, channel_id):
                    continue
                    
                # User needs to request to join this channel
                request_channels_to_join.append(channel)
                
            except Exception as e:
                request_channels_to_join.append(channel)
        
        # If user has joined all channels, proceed
        if not force_channels_to_join and not request_channels_to_join:
            return True
            
        # User needs to join channels - prepare buttons
        force_text = (
            f"⚠️ ʜᴇʏ, {message.from_user.mention} 🚀\n\n"
            "ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴊᴏɪɴᴇᴅ ᴄʜᴀɴɴᴇʟs ʏᴇᴛ. ᴘʟᴇᴀsᴇ ᴊᴏɪɴ ᴛʜᴇ ᴄʜᴀɴɴᴇʟs ʙᴇʟᴏᴡ, ᴛʜᴇɴ ᴛʀʏ ᴀɢᴀɪɴ.. !\n\n"
            "❗️ғᴀᴄɪɴɢ ᴘʀᴏʙʟᴇᴍs, ᴜsᴇ: /help"
        )
        
        buttons = []
        temp_buttons = []
        
        # Add FORCE-JOIN CHANNELS buttons
        for channel in force_channels_to_join:
            try:
                chat = await client.get_chat(channel)
                invite_link = await client.export_chat_invite_link(channel)
                btn = InlineKeyboardButton(f"👾 {chat.title}", url=invite_link)
                temp_buttons.append(btn)
                if len(temp_buttons) == 2:
                    buttons.append(temp_buttons)
                    temp_buttons = []
            except Exception as e:
                continue
        
        # Add REQUEST-JOIN CHANNELS buttons
        for channel in request_channels_to_join:
            try:
                chat = await client.get_chat(channel)
                invite_link = await client.create_chat_invite_link(channel, creates_join_request=True)
                btn = InlineKeyboardButton(f"{chat.title}", url=invite_link.invite_link)
                temp_buttons.append(btn)
                if len(temp_buttons) == 2:
                    buttons.append(temp_buttons)
                    temp_buttons = []
            except Exception as e:
                continue
        
        # Add leftovers
        if temp_buttons:
            buttons.append(temp_buttons)
        
        # Add Try Again button
        buttons.append([
            InlineKeyboardButton("♻️ ᴛʀʏ ᴀɢᴀɪɴ ♻️", url=f"https://t.me/{client.username}?start="),
            InlineKeyboardButton("❓ ᴀɴʏ ʜᴇʟᴘ", url="https://t.me/shizukawachan")
        ])
        
        # Send the message with buttons
        if buttons:
            try:
                await message.reply_photo(
                    photo=FORCE_PIC,
                    caption=force_text,
                    reply_markup=InlineKeyboardMarkup(buttons),
                    quote=True
                )
            except Exception as e:
                # Fallback to text message
                try:
                    await message.reply(
                        force_text,
                        reply_markup=InlineKeyboardMarkup(buttons),
                        quote=True
                    )
                except Exception as e:
                    pass
        
        return False
        
    except Exception as e:
        return True  # Allow access if there's an error

@Client.on_chat_join_request()
async def join_reqs(client: Client, message: ChatJoinRequest):
    """Handle join requests for channels that require approval"""
    try:
        settings = await get_settings()
        REQUEST_SUB_CHANNELS = settings.get("REQUEST_SUB_CHANNELS", [])
        
        # Convert channel IDs to integers for comparison
        request_channel_ids = []
        for channel in REQUEST_SUB_CHANNELS:
            try:
                if isinstance(channel, str) and channel.startswith('@'):
                    # Convert username to ID
                    chat = await client.get_chat(channel)
                    request_channel_ids.append(chat.id)
                else:
                    request_channel_ids.append(int(channel))
            except:
                request_channel_ids.append(channel)
        
        # Only process requests for our channels
        if message.chat.id not in request_channel_ids:
            return
        
        user_id = message.from_user.id
        channel_id = message.chat.id
        
        # Store the join request in the database
        await store_join_request(user_id, channel_id)
        
    except Exception as e:
        pass

@Client.on_chat_member_updated()
async def chat_member_updated(client: Client, update):
    """Handle when users join/leave channels"""
    try:
        # Check if user joined
        if (update.new_chat_member and 
            update.new_chat_member.status in ["member", "administrator", "owner"] and
            (not update.old_chat_member or update.old_chat_member.status not in ["member", "administrator", "owner"])):
            
            user_id = update.from_user.id
            channel_id = update.chat.id
            
            # Remove any pending request since user has joined
            await remove_join_request(user_id, channel_id)
            
    except Exception as e:
        pass

@Client.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    """Handle /start command with subscription check"""
    try:
        # Check subscription first
        if not await check_subscription(client, message):
            return
            
        user_name = message.from_user.first_name or "ᴜsᴇʀ"
        user_id = message.from_user.id
        
        welcome_text = (
            f"👋 <b>ʜᴇʏ {user_name}!</b>\n\n"
            f"🤖 <b>ɪ'ᴍ {Config.BOT_NAME}</b>\n\n"
            f"📥 <b>ɪ ᴄᴀɴ ᴅᴏᴡɴʟᴏᴀᴅ ᴠɪᴅᴇᴏs ғʀᴏᴍ:</b>\n"
            f"• ʏᴏᴜᴛᴜʙᴇ, ɪɴsᴛᴀɢʀᴀᴍ, ᴛɪᴋᴛᴏᴋ\n"
            f"• ᴘᴏʀɴʜᴜʙ, xᴠɪᴅᴇᴏs, xɴxx\n"
            f"• ᴀɴᴅ 1000+ ᴄᴏʀɴ / ᴏᴛʜᴇʀ sɪᴛᴇs!\n\n"
            f"🚀 <b>ᴊᴜsᴛ sᴇɴᴅ ᴍᴇ ᴀ ʟɪɴᴋ!</b>\n\n"
        )
        
        # Create inline keyboard with the requested button
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("ᴍᴀᴅᴇ ᴡɪᴛʜ 💓", url="https://t.me/shizukawachan")]
        ])
        
        # Send photo with caption instead of text message
        await message.reply_photo(
            photo=FORCE_PIC,
            caption=welcome_text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
        
    except Exception as e:
        # Fallback to text message if photo fails
        try:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("ᴍᴀᴅᴇ ᴡɪᴛʜ 💓", url="https://t.me/shizukawachan")]
            ])
            await message.reply_text(
                welcome_text, 
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
        except Exception as fallback_error:
            await message.reply_text("❌ <b>ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ!</b>", parse_mode=ParseMode.HTML)

# Channel management commands (Admin only)
@Client.on_message(filters.command("addchannel") & filters.private)
async def add_channel_command(client: Client, message: Message):
    """Add channel to force subscription list"""
    try:
        user_id = message.from_user.id
        
        # Check if user is admin
        if user_id not in ADMINS:
            await message.reply_text("❌ <b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴜᴛʜᴏʀɪᴢᴇᴅ!</b>", parse_mode=ParseMode.HTML)
            return
        
        # Parse command
        command_parts = message.text.split()
        if len(command_parts) < 3:
            await message.reply_text(
                "<b>📝 ᴜsᴀɢᴇ:</b>\n\n"
                "<code>/addchannel [force/request] [channel_id]</code>\n\n"
                "<b>ᴇxᴀᴍᴘʟᴇ:</b>\n"
                "<code>/addchannel force -1001234567890</code>\n"
                "<code>/addchannel request @yourchannel</code>",
                parse_mode=ParseMode.HTML
            )
            return
        
        channel_type = command_parts[1].lower()
        channel_id = command_parts[2]
        
        if channel_type not in ['force', 'request']:
            await message.reply_text("❌ <b>ɪɴᴠᴀʟɪᴅ ᴛʏᴘᴇ! ᴜsᴇ 'force' ᴏʀ 'request'</b>", parse_mode=ParseMode.HTML)
            return
        
        # Get current settings
        settings = await get_settings()
        
        if channel_type == 'force':
            force_channels = settings.get("FORCE_SUB_CHANNELS", [])
            if channel_id not in force_channels:
                force_channels.append(channel_id)
                settings["FORCE_SUB_CHANNELS"] = force_channels
                await update_settings(settings)
                await message.reply_text(f"✅ <b>ᴀᴅᴅᴇᴅ {channel_id} ᴛᴏ ғᴏʀᴄᴇ sᴜʙsᴄʀɪᴘᴛɪᴏɴ ʟɪsᴛ!</b>", parse_mode=ParseMode.HTML)
            else:
                await message.reply_text("❌ <b>ᴄʜᴀɴɴᴇʟ ᴀʟʀᴇᴀᴅʏ ɪɴ ʟɪsᴛ!</b>", parse_mode=ParseMode.HTML)
        else:
            request_channels = settings.get("REQUEST_SUB_CHANNELS", [])
            if channel_id not in request_channels:
                request_channels.append(channel_id)
                settings["REQUEST_SUB_CHANNELS"] = request_channels
                await update_settings(settings)
                await message.reply_text(f"✅ <b>ᴀᴅᴅᴇᴅ {channel_id} ᴛᴏ ʀᴇǫᴜᴇsᴛ sᴜʙsᴄʀɪᴘᴛɪᴏɴ ʟɪsᴛ!</b>", parse_mode=ParseMode.HTML)
            else:
                await message.reply_text("❌ <b>ᴄʜᴀɴɴᴇʟ ᴀʟʀᴇᴀᴅʏ ɪɴ ʟɪsᴛ!</b>", parse_mode=ParseMode.HTML)
        
    except Exception as e:
        await message.reply_text("❌ <b>ᴇʀʀᴏʀ ᴀᴅᴅɪɴɢ ᴄʜᴀɴɴᴇʟ!</b>", parse_mode=ParseMode.HTML)

@Client.on_message(filters.command("removechannel") & filters.private)
async def remove_channel_command(client: Client, message: Message):
    """Remove channel from subscription list"""
    try:
        user_id = message.from_user.id
        
        # Check if user is admin
        if user_id not in ADMINS:
            await message.reply_text("❌ <b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴜᴛʜᴏʀɪᴢᴇᴅ!</b>", parse_mode=ParseMode.HTML)
            return
        
        # Parse command
        command_parts = message.text.split()
        if len(command_parts) < 3:
            await message.reply_text(
                "<b>📝 ᴜsᴀɢᴇ:</b>\n\n"
                "<code>/removechannel [force/request] [channel_id]</code>\n\n"
                "<b>ᴇxᴀᴍᴘʟᴇ:</b>\n"
                "<code>/removechannel force -1001234567890</code>\n"
                "<code>/removechannel request @yourchannel</code>",
                parse_mode=ParseMode.HTML
            )
            return
        
        channel_type = command_parts[1].lower()
        channel_id = command_parts[2]
        
        if channel_type not in ['force', 'request']:
            await message.reply_text("❌ <b>ɪɴᴠᴀʟɪᴅ ᴛʏᴘᴇ! ᴜsᴇ 'force' ᴏʀ 'request'</b>", parse_mode=ParseMode.HTML)
            return
        
        # Get current settings
        settings = await get_settings()
        
        if channel_type == 'force':
            force_channels = settings.get("FORCE_SUB_CHANNELS", [])
            if channel_id in force_channels:
                force_channels.remove(channel_id)
                settings["FORCE_SUB_CHANNELS"] = force_channels
                await update_settings(settings)
                await message.reply_text(f"✅ <b>ʀᴇᴍᴏᴠᴇᴅ {channel_id} ғʀᴏᴍ ғᴏʀᴄᴇ sᴜʙsᴄʀɪᴘᴛɪᴏɴ ʟɪsᴛ!</b>", parse_mode=ParseMode.HTML)
            else:
                await message.reply_text("❌ <b>ᴄʜᴀɴɴᴇʟ ɴᴏᴛ ғᴏᴜɴᴅ ɪɴ ʟɪsᴛ!</b>", parse_mode=ParseMode.HTML)
        else:
            request_channels = settings.get("REQUEST_SUB_CHANNELS", [])
            if channel_id in request_channels:
                request_channels.remove(channel_id)
                settings["REQUEST_SUB_CHANNELS"] = request_channels
                await update_settings(settings)
                await message.reply_text(f"✅ <b>ʀᴇᴍᴏᴠᴇᴅ {channel_id} ғʀᴏᴍ ʀᴇǫᴜᴇsᴛ sᴜʙsᴄʀɪᴘᴛɪᴏɴ ʟɪsᴛ!</b>", parse_mode=ParseMode.HTML)
            else:
                await message.reply_text("❌ <b>ᴄʜᴀɴɴᴇʟ ɴᴏᴛ ғᴏᴜɴᴅ ɪɴ ʟɪsᴛ!</b>", parse_mode=ParseMode.HTML)
        
    except Exception as e:
        await message.reply_text("❌ <b>ᴇʀʀᴏʀ ʀᴇᴍᴏᴠɪɴɢ ᴄʜᴀɴɴᴇʟ!</b>", parse_mode=ParseMode.HTML)

@Client.on_message(filters.command("showchannels") & filters.private)
async def show_channels_command(client: Client, message: Message):
    """Show all subscription channels"""
    try:
        user_id = message.from_user.id
        
        # Check if user is admin
        if user_id not in ADMINS:
            await message.reply_text("❌ <b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴜᴛʜᴏʀɪᴢᴇᴅ!</b>", parse_mode=ParseMode.HTML)
            return
        
        # Get current settings
        settings = await get_settings()
        force_channels = settings.get("FORCE_SUB_CHANNELS", [])
        request_channels = settings.get("REQUEST_SUB_CHANNELS", [])
        
        channels_text = "<b>📋 sᴜʙsᴄʀɪᴘᴛɪᴏɴ ᴄʜᴀɴɴᴇʟs</b>\n\n"
        
        # Show force subscription channels
        if force_channels:
            channels_text += "<b>🔒 ғᴏʀᴄᴇ sᴜʙsᴄʀɪᴘᴛɪᴏɴ ᴄʜᴀɴɴᴇʟs:</b>\n"
            for i, channel in enumerate(force_channels, 1):
                try:
                    chat = await client.get_chat(channel)
                    channels_text += f"{i}. <code>{channel}</code> - {chat.title}\n"
                except Exception as e:
                    channels_text += f"{i}. <code>{channel}</code> - ᴇʀʀᴏʀ ɢᴇᴛᴛɪɴɢ ɪɴғᴏ\n"
            channels_text += "\n"
        else:
            channels_text += "<b>🔒 ғᴏʀᴄᴇ sᴜʙsᴄʀɪᴘᴛɪᴏɴ ᴄʜᴀɴɴᴇʟs:</b> ɴᴏɴᴇ\n\n"
        
        # Show request subscription channels
        if request_channels:
            channels_text += "<b>📝 ʀᴇǫᴜᴇsᴛ sᴜʙsᴄʀɪᴘᴛɪᴏɴ ᴄʜᴀɴɴᴇʟs:</b>\n"
            for i, channel in enumerate(request_channels, 1):
                try:
                    chat = await client.get_chat(channel)
                    channels_text += f"{i}. <code>{channel}</code> - {chat.title}\n"
                except Exception as e:
                    channels_text += f"{i}. <code>{channel}</code> - ᴇʀʀᴏʀ ɢᴇᴛᴛɪɴɢ ɪɴғᴏ\n"
            channels_text += "\n"
        else:
            channels_text += "<b>📝 ʀᴇǫᴜᴇsᴛ sᴜʙsᴄʀɪᴘᴛɪᴏɴ ᴄʜᴀɴɴᴇʟs:</b> ɴᴏɴᴇ\n\n"
        
        channels_text += (
            "<b>💡 ᴄᴏᴍᴍᴀɴᴅs:</b>\n"
            "• <code>/addchannel force [channel_id]</code>\n"
            "• <code>/addchannel request [channel_id]</code>\n"
            "• <code>/removechannel force [channel_id]</code>\n"
            "• <code>/removechannel request [channel_id]</code>"
        )
        
        await message.reply_text(channels_text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        await message.reply_text("❌ <b>ᴇʀʀᴏʀ sʜᴏᴡɪɴɢ ᴄʜᴀɴɴᴇʟs!</b>", parse_mode=ParseMode.HTML)

@Client.on_message(filters.command("help") & filters.private)
async def help_command(client: Client, message: Message):
    """Show help message"""
    try:
        user_id = message.from_user.id
        
        if user_id in ADMINS:
            help_text = (
                "<b>🤖 ʙᴏᴛ ʜᴇʟᴘ - ᴀᴅᴍɪɴ</b>\n\n"
                "<b>👤 ᴜsᴇʀ ᴄᴏᴍᴍᴀɴᴅs:</b>\n"
                "• /start - sᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ\n"
                "• /stats - sʜᴏᴡ ʙᴏᴛ sᴛᴀᴛɪsᴛɪᴄs\n"
                "• /mystats - sʜᴏᴡ ʏᴏᴜʀ sᴛᴀᴛɪsᴛɪᴄs\n"
                "• /history - sʜᴏᴡ ᴅᴏᴡɴʟᴏᴀᴅ ʜɪsᴛᴏʀʏ\n"
                "• /leaderboard - sʜᴏᴡ ᴛᴏᴘ ᴜsᴇʀs\n\n"
                "<b>👑 ᴀᴅᴍɪɴ ᴄᴏᴍᴍᴀɴᴅs:</b>\n"
                "• /addchannel - ᴀᴅᴅ sᴜʙsᴄʀɪᴘᴛɪᴏɴ ᴄʜᴀɴɴᴇʟ\n"
                "• /removechannel - ʀᴇᴍᴏᴠᴇ sᴜʙsᴄʀɪᴘᴛɪᴏɴ ᴄʜᴀɴɴᴇʟ\n"
                "• /showchannels - sʜᴏᴡ ᴀʟʟ ᴄʜᴀɴɴᴇʟs\n\n"
                "<b>📥 ᴅᴏᴡɴʟᴏᴀᴅ:</b>\n"
                "sᴇɴᴅ ᴀɴʏ ᴠɪᴅᴇᴏ ʟɪɴᴋ ᴛᴏ ᴅᴏᴡɴʟᴏᴀᴅ!"
            )
        else:
            help_text = (
                "<b>🤖 ʙᴏᴛ ʜᴇʟᴘ</b>\n\n"
                "<b>📋 ᴀᴠᴀɪʟᴀʙʟᴇ ᴄᴏᴍᴍᴀɴᴅs:</b>\n"
                "• /start - sᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ\n"
                "• /stats - sʜᴏᴡ ʙᴏᴛ sᴛᴀᴛɪsᴛɪᴄs\n"
                "• /history - sʜᴏᴡ ᴅᴏᴡɴʟᴏᴀᴅ ʜɪsᴛᴏʀʏ\n"
                "• /leaderboard - sʜᴏᴡ ᴛᴏᴘ ᴜsᴇʀs\n"
                "• /help - sʜᴏᴡ ᴛʜɪs ʜᴇʟᴘ\n\n"
                "<b>📥 ʜᴏᴡ ᴛᴏ ᴜsᴇ:</b>\n"
                "sɪᴍᴘʟʏ sᴇɴᴅ ᴍᴇ ᴀ ᴠɪᴅᴇᴏ ʟɪɴᴋ ғʀᴏᴍ:\n"
                "• ʏᴏᴜᴛᴜʙᴇ, ɪɴsᴛᴀɢʀᴀᴍ, ᴛɪᴋᴛᴏᴋ\n"
                "• ᴘᴏʀɴʜᴜʙ, xᴠɪᴅᴇᴏs, xɴxx\n"
                "• ᴀɴᴅ 1000+ ᴏᴛʜᴇʀ sɪᴛᴇs!\n\n"
                "<b>❓ ɴᴇᴇᴅ sᴜᴘᴘᴏʀᴛ?</b>\n"
                "ᴊᴏɪɴ: https://t.me/shizukawachan"
            )
        
        # Create inline keyboard
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("ᴍᴀᴅᴇ ᴡɪᴛʜ 💓", url="https://t.me/shizukawachan")]
        ])
        
        await message.reply_text(help_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        
    except Exception as e:
        await message.reply_text("❌ <b>ᴇʀʀᴏʀ sʜᴏᴡɪɴɢ ʜᴇʟᴘ!</b>", parse_mode=ParseMode.HTML)

@Client.on_message(filters.command("ping") & filters.private)
async def ping_command(client: Client, message: Message):
    """Handle /ping command"""
    try:
        import time
        start_time = time.time()
        
        # Send initial message
        sent_message = await message.reply_text("🏓 ᴘɪɴɢɪɴɢ...")
        
        # Calculate response time
        end_time = time.time()
        response_time = (end_time - start_time) * 1000  # Convert to milliseconds
        
        # Update with final response
        ping_text = (
            f"🏓 <b>ᴘᴏɴɢ!</b>\n\n"
            f"⚡ <b>ʀᴇsᴘᴏɴsᴇ ᴛɪᴍᴇ:</b> <code>{response_time:.2f}ᴍs</code>\n"
        )
        
        await sent_message.edit_text(ping_text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        await message.reply_text("❌ <b>ᴇʀʀᴏʀ</b>", parse_mode=ParseMode.HTML)


@Client.on_message(filters.command("fixstats") & filters.private)
async def fix_stats_command(client: Client, message: Message):
    """Fix user stats by recalculating from download history"""
    try:
        user_id = message.from_user.id
        
        # Get user's download history
        history = await get_user_download_history(user_id, 1000)  # Get all history
        
        if not history:
            await message.reply_text("❌ <b>ɴᴏ ᴅᴏᴡɴʟᴏᴀᴅ ʜɪsᴛᴏʀʏ ғᴏᴜɴᴅ</b>", parse_mode=ParseMode.HTML)
            return
        
        # Calculate totals from history
        total_downloads = len(history)
        total_size = sum(item.get('file_size', 0) for item in history)
        
        # Calculate favorite sites
        favorite_sites = {}
        for item in history:
            site = item.get('site', 'unknown')
            favorite_sites[site] = favorite_sites.get(site, 0) + 1
        
        # Update user with calculated stats
        await user_data.update_one(
            {'_id': user_id},
            {
                '$set': {
                    'total_downloads': total_downloads,
                    'total_size': total_size,
                    'favorite_sites': favorite_sites,
                    'last_activity': datetime.now()
                }
            }
        )
        
        def format_size(size_bytes):
            if size_bytes == 0:
                return "0 B"
            size_names = ["B", "KB", "MB", "GB", "TB"]
            import math
            i = int(math.floor(math.log(size_bytes, 1024)))
            p = math.pow(1024, i)
            s = round(size_bytes / p, 2)
            return f"{s} {size_names[i]}"
        
        await message.reply_text(
            f"✅ <b>sᴛᴀᴛs ғɪxᴇᴅ!</b>\n\n"
            f"📥 <b>ᴛᴏᴛᴀʟ ᴅᴏᴡɴʟᴏᴀᴅs:</b> {total_downloads:,}\n"
            f"💾 <b>ᴛᴏᴛᴀʟ sɪᴢᴇ:</b> {format_size(total_size)}\n"
            f"🌐 <b>sɪᴛᴇs:</b> {len(favorite_sites)}",
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        print(f"❌ Error fixing stats: {e}")
        await message.reply_text("❌ <b>ᴇʀʀᴏʀ ғɪxɪɴɢ sᴛᴀᴛs</b>", parse_mode=ParseMode.HTML)


@Client.on_message(filters.command("clearrequests") & filters.private)
async def clear_requests_command(client: Client, message: Message):
    """Clear pending join requests (Admin only)"""
    try:
        user_id = message.from_user.id
        
        # Check if user is admin
        if user_id not in ADMINS:
            await message.reply_text("❌ <b>ʏᴏᴜ ᴀʀᴇ ɴᴏᴛ ᴀᴜᴛʜᴏʀɪᴢᴇᴅ!</b>", parse_mode=ParseMode.HTML)
            return
        
        # Parse command
        command_parts = message.text.split()
        
        if len(command_parts) == 1:
            # Show usage
            await message.reply_text(
                "<b>📝 ᴜsᴀɢᴇ:</b>\n\n"
                "<code>/clearrequests all</code> - Clear all pending requests\n"
                "<code>/clearrequests [channel_id]</code> - Clear requests for specific channel\n"
                "<code>/clearrequests [user_id]</code> - Clear requests for specific user\n"
                "<code>/clearrequests [user_id] [channel_id]</code> - Clear specific request\n\n"
                "<b>ᴇxᴀᴍᴘʟᴇs:</b>\n"
                "<code>/clearrequests all</code>\n"
                "<code>/clearrequests -1001234567890</code>\n"
                "<code>/clearrequests 123456789</code>\n"
                "<code>/clearrequests 123456789 -1001234567890</code>",
                parse_mode=ParseMode.HTML
            )
            return
        
        if command_parts[1].lower() == "all":
            # Clear all pending requests
            from database import join_requests
            result = await join_requests.delete_many({"status": "pending"})
            await message.reply_text(
                f"✅ <b>ᴄʟᴇᴀʀᴇᴅ {result.deleted_count} ᴘᴇɴᴅɪɴɢ ʀᴇǫᴜᴇsᴛs!</b>",
                parse_mode=ParseMode.HTML
            )
            
        elif len(command_parts) == 2:
            # Clear requests for specific channel or user
            target_id = command_parts[1]
            
            try:
                target_id = int(target_id)
            except ValueError:
                await message.reply_text("❌ <b>ɪɴᴠᴀʟɪᴅ ɪᴅ ғᴏʀᴍᴀᴛ!</b>", parse_mode=ParseMode.HTML)
                return
            
            from database import join_requests
            
            # Check if it's a channel ID (negative) or user ID (positive)
            if target_id < 0:
                # Channel ID
                result = await join_requests.delete_many({
                    "channel_id": target_id,
                    "status": "pending"
                })
                await message.reply_text(
                    f"✅ <b>ᴄʟᴇᴀʀᴇᴅ {result.deleted_count} ᴘᴇɴᴅɪɴɢ ʀᴇǫᴜᴇsᴛs ғᴏʀ ᴄʜᴀɴɴᴇʟ {target_id}!</b>",
                    parse_mode=ParseMode.HTML
                )
            else:
                # User ID
                result = await join_requests.delete_many({
                    "user_id": target_id,
                    "status": "pending"
                })
                await message.reply_text(
                    f"✅ <b>ᴄʟᴇᴀʀᴇᴅ {result.deleted_count} ᴘᴇɴᴅɪɴɢ ʀᴇǫᴜᴇsᴛs ғᴏʀ ᴜsᴇʀ {target_id}!</b>",
                    parse_mode=ParseMode.HTML
                )
                
        elif len(command_parts) == 3:
            # Clear specific request
            try:
                user_id_target = int(command_parts[1])
                channel_id_target = int(command_parts[2])
            except ValueError:
                await message.reply_text("❌ <b>ɪɴᴠᴀʟɪᴅ ɪᴅ ғᴏʀᴍᴀᴛ!</b>", parse_mode=ParseMode.HTML)
                return
            
            from database import join_requests
            result = await join_requests.delete_many({
                "user_id": user_id_target,
                "channel_id": channel_id_target,
                "status": "pending"
            })
            
            if result.deleted_count > 0:
                await message.reply_text(
                    f"✅ <b>ᴄʟᴇᴀʀᴇᴅ ᴘᴇɴᴅɪɴɢ ʀᴇǫᴜᴇsᴛ ғᴏʀ ᴜsᴇʀ {user_id_target} ɪɴ ᴄʜᴀɴɴᴇʟ {channel_id_target}!</b>",
                    parse_mode=ParseMode.HTML
                )
            else:
                await message.reply_text(
                    f"❌ <b>ɴᴏ ᴘᴇɴᴅɪɴɢ ʀᴇǫᴜᴇsᴛ ғᴏᴜɴᴅ ғᴏʀ ᴜsᴇʀ {user_id_target} ɪɴ ᴄʜᴀɴɴᴇʟ {channel_id_target}!</b>",
                    parse_mode=ParseMode.HTML
                )
        else:
            await message.reply_text("❌ <b>ɪɴᴠᴀʟɪᴅ ᴄᴏᴍᴍᴀɴᴅ ғᴏʀᴍᴀᴛ!</b>", parse_mode=ParseMode.HTML)
        
    except Exception as e:
        print(f"❌ Error in clear requests command: {e}")
        await message.reply_text("❌ <b>ᴇʀʀᴏʀ ᴄʟᴇᴀʀɪɴɢ ʀᴇǫᴜᴇsᴛs!</b>", parse_mode=ParseMode.HTML)
