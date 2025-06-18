from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ChatJoinRequest
from pyrogram.errors import UserNotParticipant
from pyrogram.enums import ParseMode
from config import Config
import os
from database import *
from datetime import datetime
from helper_func import *

OWNER_ID = int(os.environ.get("OWNER_ID", "7560922302"))
OWNER_TAG = os.environ.get("OWNER_TAG", "shizukawachan")
ADMIN_LIST = os.environ.get("ADMINS", "").split()
ADMINS = [int(admin) for admin in ADMIN_LIST if admin.isdigit()]
ADMINS.append(OWNER_ID)

async def check_subscription(client: Client, message: Message) -> bool:
    """Check if user is subscribed to required channels"""
    try:
        settings = await get_settings()
        FORCE_SUB_CHANNELS = settings.get("FORCE_SUB_CHANNELS", [])
        REQUEST_SUB_CHANNELS = settings.get("REQUEST_SUB_CHANNELS", [])
        user_id = message.from_user.id
        
        if user_id in ADMINS:
            return True
        
        if not FORCE_SUB_CHANNELS and not REQUEST_SUB_CHANNELS:
            return True
            
        force_channels_to_join = []
        request_channels_to_join = []
        
        # Check force sub channels
        for channel_data in FORCE_SUB_CHANNELS:
            try:
                if isinstance(channel_data, dict):
                    channel_id = channel_data.get('id')
                    channel_status = channel_data.get('status', 'active')
                    
                    if channel_status == 'error':
                        print(f"⚠️ Skipping force channel with error: {channel_id}")
                        continue
                else:
                    channel_id = channel_data
                
                member = await client.get_chat_member(channel_id, user_id)
                if member.status not in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.MEMBER]:
                    force_channels_to_join.append(channel_data)
                    
            except UserNotParticipant:
                force_channels_to_join.append(channel_data)
            except Exception as e:
                print(f"❌ Error checking force channel {channel_id}: {e}")
                force_channels_to_join.append(channel_data)
                
        # Check request channels
        for channel_data in REQUEST_SUB_CHANNELS:
            try:
                if isinstance(channel_data, dict):
                    channel_id = channel_data.get('id')
                    channel_status = channel_data.get('status', 'active')
                    
                    if channel_status == 'error':
                        print(f"⚠️ Skipping request channel with error: {channel_id}")
                        continue
                else:
                    channel_id = channel_data
                
                if isinstance(channel_id, str) and channel_id.lstrip('-').isdigit():
                    channel_id_int = int(channel_id)
                else:
                    channel_id_int = channel_id
                
                try:
                    member = await client.get_chat_member(channel_id, user_id)
                    if member.status in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.MEMBER]:
                        await remove_join_request(user_id, channel_id_int)
                        continue
                except UserNotParticipant:
                    pass
                
                if await has_pending_request(user_id, channel_id_int):
                    continue
                    
                request_channels_to_join.append(channel_data)
                
            except Exception as e:
                print(f"❌ Error checking request channel {channel_id}: {e}")
                request_channels_to_join.append(channel_data)
        
        if not force_channels_to_join and not request_channels_to_join:
            return True
            
        force_text = (
            f"⚠️ ʜᴇʏ, {message.from_user.mention} 🚀\n\n"
            "ʏᴏᴜ ʜᴀᴠᴇɴ'ᴛ ᴊᴏɪɴᴇᴅ ᴄʜᴀɴɴᴇʟs ʏᴇᴛ. ᴘʟᴇᴀsᴇ ᴊᴏɪɴ ᴛʜᴇ ᴄʜᴀɴɴᴇʟs ʙᴇʟᴏᴡ, ᴛʜᴇɴ ᴛʀʏ ᴀɢᴀɪɴ.. !\n\n"
            "❗️ғᴀᴄɪɴɢ ᴘʀᴏʙʟᴇᴍs, ᴜsᴇ: /help"
        )
        
        buttons = []
        temp_buttons = []
        
        # Add FORCE-JOIN CHANNELS buttons using stored links
        for channel_data in force_channels_to_join:
            try:
                if isinstance(channel_data, dict):
                    channel_id = channel_data.get('id')
                    stored_link = channel_data.get('invite_link')
                else:
                    channel_id = channel_data
                    stored_link = None
                
                chat = await client.get_chat(channel_id)
                
                # Use stored link if available
                if stored_link:
                    invite_link = stored_link
                else:
                    # Fallback: try to get new link
                    try:
                        invite_link = await client.export_chat_invite_link(channel_id)
                    except Exception:
                        if chat.username:
                            invite_link = f"https://t.me/{chat.username}"
                        else:
                            clean_id = str(channel_id).replace('-100', '')
                            invite_link = f"https://t.me/c/{clean_id}"
                
                btn = InlineKeyboardButton(f"👾 {chat.title}", url=invite_link)
                temp_buttons.append(btn)
                if len(temp_buttons) == 2:
                    buttons.append(temp_buttons)
                    temp_buttons = []
                    
            except Exception as e:
                print(f"❌ Error creating force channel button: {e}")
                continue
        
        # Add REQUEST-JOIN CHANNELS buttons using stored links
        for channel_data in request_channels_to_join:
            try:
                if isinstance(channel_data, dict):
                    channel_id = channel_data.get('id')
                    stored_link = channel_data.get('invite_link')
                else:
                    channel_id = channel_data
                    stored_link = None
                
                chat = await client.get_chat(channel_id)
                
                # Use stored link if available
                if stored_link:
                    invite_link = stored_link
                else:
                    # Fallback: try to create request link
                    try:
                        link_obj = await client.create_chat_invite_link(channel_id, creates_join_request=True)
                        invite_link = link_obj.invite_link
                    except Exception:
                        if chat.username:
                            invite_link = f"https://t.me/{chat.username}"
                        else:
                            clean_id = str(channel_id).replace('-100', '')
                            invite_link = f"https://t.me/c/{clean_id}"
                
                btn = InlineKeyboardButton(f"📝 {chat.title}", url=invite_link)
                temp_buttons.append(btn)
                if len(temp_buttons) == 2:
                    buttons.append(temp_buttons)
                    temp_buttons = []
                    
            except Exception as e:
                print(f"❌ Error creating request channel button: {e}")
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
                    photo=Config.FORCE_PIC,
                    caption=force_text,
                    reply_markup=InlineKeyboardMarkup(buttons),
                    quote=True
                )
            except Exception as e:
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
        print(f"❌ Error in check_subscription: {e}")
        return True

@Client.on_chat_join_request()
async def join_reqs(client: Client, message: ChatJoinRequest):
    """Handle join requests for channels that require approval"""
    try:
        settings = await get_settings()
        REQUEST_SUB_CHANNELS = settings.get("REQUEST_SUB_CHANNELS", [])
        
        request_channel_ids = []
        for channel_data in REQUEST_SUB_CHANNELS:
            try:
                if isinstance(channel_data, dict):
                    channel_id = channel_data.get('id')
                else:
                    channel_id = channel_data
                    
                if isinstance(channel_id, str) and channel_id.startswith('@'):
                    chat = await client.get_chat(channel_id)
                    request_channel_ids.append(chat.id)
                else:
                    request_channel_ids.append(int(channel_id))
            except:
                if isinstance(channel_data, dict):
                    request_channel_ids.append(channel_data.get('id'))
                else:
                    request_channel_ids.append(channel_data)
        
        if message.chat.id not in request_channel_ids:
            return
        
        user_id = message.from_user.id
        channel_id = message.chat.id
        
        await store_join_request(user_id, channel_id)
        
    except Exception as e:
        print(f"❌ Error in join_reqs: {e}")

@Client.on_chat_member_updated()
async def chat_member_updated(client: Client, update):
    """Handle when users join/leave channels"""
    try:
        if (update.new_chat_member and 
            update.new_chat_member.status in ["member", "administrator", "owner"] and
            (not update.old_chat_member or update.old_chat_member.status not in ["member", "administrator", "owner"])):
            
            user_id = update.from_user.id
            channel_id = update.chat.id
            
            await remove_join_request(user_id, channel_id)
            
    except Exception as e:
        print(f"❌ Error in chat_member_updated: {e}")
