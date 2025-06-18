from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ChatJoinRequest
from pyrogram.errors import UserNotParticipant
from pyrogram.enums import ParseMode
from config import Config
import os
from database import *
from datetime import datetime
import sys 
from commands.download import *
from helper_func import *
import asyncio
from pyrogram.errors import ChatAdminRequired, PeerIdInvalid, ChannelInvalid, UserNotParticipant

async def update_settings(settings_dict: dict):
    """Update bot settings in database"""
    try:
        settings_dict['updated_at'] = datetime.now()
        await settings_data.update_one(
            {'_id': 'bot_settings'},
            {'$set': settings_dict},
            upsert=True
        )
        return True
    except Exception as e:
        logging.error(f"Error updating settings: {e}")
        return False

async def validate_channel_access(client: Client, channel_id: str):
    """Validate bot's access to channel and get invite link"""
    try:
        # Try to get chat info
        chat = await client.get_chat(channel_id)
        
        # Check if bot is admin
        try:
            bot_member = await client.get_chat_member(channel_id, "me")
            if bot_member.status not in ["administrator", "creator"]:
                return False, f"Bot is not admin in {chat.title}", None
        except Exception as e:
            return False, f"Cannot check bot status in {chat.title}: {str(e)}", None
        
        # Try to get invite link
        invite_link = None
        try:
            # Try to get existing invite link
            invite_link = chat.invite_link
            
            # If no invite link, try to create one
            if not invite_link:
                try:
                    link_obj = await client.create_chat_invite_link(channel_id)
                    invite_link = link_obj.invite_link
                except Exception as e:
                    print(f"⚠️ Could not create invite link for {chat.title}: {e}")
                    # Use channel username if available
                    if chat.username:
                        invite_link = f"https://t.me/{chat.username}"
                    else:
                        invite_link = f"https://t.me/c/{str(channel_id).replace('-100', '')}"
                        
        except Exception as e:
            print(f"⚠️ Could not get invite link for {chat.title}: {e}")
            if chat.username:
                invite_link = f"https://t.me/{chat.username}"
        
        return True, f"✅ {chat.title}", invite_link
        
    except ChatAdminRequired:
        return False, "Bot needs admin permissions", None
    except (PeerIdInvalid, ChannelInvalid):
        return False, "Invalid channel ID", None
    except Exception as e:
        return False, f"Error: {str(e)}", None

@Client.on_message(filters.command("addchannel") & filters.private)
async def add_channel_command(client: Client, message: Message):
    """Add channel to force subscription list with enhanced validation"""
    
    # Check if user is admin
    if message.from_user.id not in Config.ADMINS:
        await message.reply_text("❌ Access denied.")
        return
        
    try:
        # Parse command
        command_parts = message.text.split()
        if len(command_parts) < 3:
            await message.reply_text(
                "<b>📝 ᴜsᴀɢᴇ:</b>\n\n"
                "<code>/addchannel [force/request] [channel_id_or_username]</code>\n\n"
                "<b>ᴇxᴀᴍᴘʟᴇs:</b>\n"
                "<code>/addchannel force -1001234567890</code>\n"
                "<code>/addchannel request @yourchannel</code>\n"
                "<code>/addchannel force https://t.me/yourchannel</code>",
                parse_mode=ParseMode.HTML
            )
            return
        
        channel_type = command_parts[1].lower()
        channel_input = command_parts[2]
        
        if channel_type not in ['force', 'request']:
            await message.reply_text("❌ <b>ɪɴᴠᴀʟɪᴅ ᴛʏᴘᴇ! ᴜsᴇ 'force' ᴏʀ 'request'</b>", parse_mode=ParseMode.HTML)
            return
        
        # Process channel input (handle @username, t.me links, or direct ID)
        channel_id = channel_input
        if channel_input.startswith('@'):
            channel_id = channel_input
        elif 't.me/' in channel_input:
            # Extract username from t.me link
            channel_id = '@' + channel_input.split('/')[-1]
        elif not channel_input.startswith('-'):
            # If it's just a username without @
            channel_id = '@' + channel_input
        
        # Show processing message
        processing_msg = await message.reply_text(
            f"<b>🔄 ᴘʀᴏᴄᴇssɪɴɢ ᴄʜᴀɴɴᴇʟ...</b>\n\n"
            f"<b>📋 ᴛʏᴘᴇ:</b> {channel_type.upper()}\n"
            f"<b>🆔 ᴄʜᴀɴɴᴇʟ:</b> <code>{channel_id}</code>\n\n"
            f"<i>⏳ ᴠᴀʟɪᴅᴀᴛɪɴɢ ᴀᴄᴄᴇss...</i>",
            parse_mode=ParseMode.HTML
        )
        
        # Validate channel access
        is_valid, status_msg, invite_link = await validate_channel_access(client, channel_id)
        
        if not is_valid:
            await processing_msg.edit_text(
                f"<b>❌ ᴄʜᴀɴɴᴇʟ ᴠᴀʟɪᴅᴀᴛɪᴏɴ ғᴀɪʟᴇᴅ</b>\n\n"
                f"<b>🆔 ᴄʜᴀɴɴᴇʟ:</b> <code>{channel_id}</code>\n"
                f"<b>❌ ᴇʀʀᴏʀ:</b> {status_msg}\n\n"
                f"<b>💡 sᴏʟᴜᴛɪᴏɴs:</b>\n"
                f"• ᴀᴅᴅ ʙᴏᴛ ᴀs ᴀᴅᴍɪɴ ɪɴ ᴄʜᴀɴɴᴇʟ\n"
                f"• ᴄʜᴇᴄᴋ ᴄʜᴀɴɴᴇʟ ɪᴅ/ᴜsᴇʀɴᴀᴍᴇ\n"
                f"• ᴇɴsᴜʀᴇ ᴄʜᴀɴɴᴇʟ ᴇxɪsᴛs",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Get current settings
        settings = await get_settings()
        
        # Add channel to appropriate list
        if channel_type == 'force':
            force_channels = settings.get("FORCE_SUB_CHANNELS", [])
            
            # Check if channel already exists
            channel_exists = False
            for existing_channel in force_channels:
                if isinstance(existing_channel, dict):
                    if existing_channel.get('id') == channel_id:
                        channel_exists = True
                        break
                elif existing_channel == channel_id:
                    channel_exists = True
                    break
            
            if channel_exists:
                await processing_msg.edit_text(
                    f"<b>⚠️ ᴄʜᴀɴɴᴇʟ ᴀʟʀᴇᴀᴅʏ ᴇxɪsᴛs</b>\n\n"
                    f"<b>🆔 ᴄʜᴀɴɴᴇʟ:</b> <code>{channel_id}</code>\n"
                    f"<b>📋 ᴛʏᴘᴇ:</b> ғᴏʀᴄᴇ sᴜʙsᴄʀɪᴘᴛɪᴏɴ",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Add channel with metadata
            channel_data = {
                'id': channel_id,
                'invite_link': invite_link,
                'added_at': datetime.now().isoformat(),
                'added_by': message.from_user.id,
                'status': 'active'
            }
            
            force_channels.append(channel_data)
            settings["FORCE_SUB_CHANNELS"] = force_channels
            
        else:  # request type
            request_channels = settings.get("REQUEST_SUB_CHANNELS", [])
            
            # Check if channel already exists
            channel_exists = False
            for existing_channel in request_channels:
                if isinstance(existing_channel, dict):
                    if existing_channel.get('id') == channel_id:
                        channel_exists = True
                        break
                elif existing_channel == channel_id:
                    channel_exists = True
                    break
            
            if channel_exists:
                await processing_msg.edit_text(
                    f"<b>⚠️ ᴄʜᴀɴɴᴇʟ ᴀʟʀᴇᴀᴅʏ ᴇxɪsᴛs</b>\n\n"
                    f"<b>🆔 ᴄʜᴀɴɴᴇʟ:</b> <code>{channel_id}</code>\n"
                    f"<b>📋 ᴛʏᴘᴇ:</b> ʀᴇǫᴜᴇsᴛ sᴜʙsᴄʀɪᴘᴛɪᴏɴ",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Add channel with metadata
            channel_data = {
                'id': channel_id,
                'invite_link': invite_link,
                'added_at': datetime.now().isoformat(),
                'added_by': message.from_user.id,
                'status': 'active'
            }
            
            request_channels.append(channel_data)
            settings["REQUEST_SUB_CHANNELS"] = request_channels
        
        # Update settings in database
        success = await update_settings(settings)
        
        if success:
            await processing_msg.edit_text(
                f"<b>✅ ᴄʜᴀɴɴᴇʟ ᴀᴅᴅᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!</b>\n\n"
                f"<b>📋 ᴛʏᴘᴇ:</b> {channel_type.upper()}\n"
                f"<b>🆔 ᴄʜᴀɴɴᴇʟ:</b> <code>{channel_id}</code>\n"
                f"<b>📺 ɴᴀᴍᴇ:</b> {status_msg}\n"
                f"<b>🔗 ɪɴᴠɪᴛᴇ ʟɪɴᴋ:</b> {'✅ ᴀᴠᴀɪʟᴀʙʟᴇ' if invite_link else '❌ ɴᴏᴛ ᴀᴠᴀɪʟᴀʙʟᴇ'}\n"
                f"<b>⏰ ᴀᴅᴅᴇᴅ:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                parse_mode=ParseMode.HTML
            )
        else:
            await processing_msg.edit_text(
                f"<b>❌ ғᴀɪʟᴇᴅ ᴛᴏ sᴀᴠᴇ sᴇᴛᴛɪɴɢs</b>\n\n"
                f"<b>🆔 ᴄʜᴀɴɴᴇʟ:</b> <code>{channel_id}</code>\n"
                f"<b>❌ ᴇʀʀᴏʀ:</b> ᴅᴀᴛᴀʙᴀsᴇ ᴇʀʀᴏʀ",
                parse_mode=ParseMode.HTML
            )
        
    except Exception as e:
        print(f"❌ Error in add_channel_command: {e}")
        await message.reply_text(
            f"<b>❌ ᴜɴᴇxᴘᴇᴄᴛᴇᴅ ᴇʀʀᴏʀ</b>\n\n"
            f"<code>{str(e)}</code>",
            parse_mode=ParseMode.HTML
        )


@Client.on_message(filters.command("removechannel") & filters.private)
async def remove_channel_command(client: Client, message: Message):
    """Remove channel from subscription list"""
    try:
        
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
        # Get current settings
        settings = await get_settings()
        force_channels = settings.get("FORCE_SUB_CHANNELS", [])
        request_channels = settings.get("REQUEST_SUB_CHANNELS", [])
        
        channels_text = "<b>📋 sᴜʙsᴄʀɪᴘᴛɪᴏɴ ᴄʜᴀɴɴᴇʟs</b>\n\n"
        
        # Show force subscription channels
        if force_channels:
            channels_text += "<b>🔒 ғᴏʀᴄᴇ sᴜʙsᴄʀɪᴘᴛɪᴏɴ ᴄʜᴀɴɴᴇʟs:</b>\n"
            for i, channel_data in enumerate(force_channels, 1):
                try:
                    if isinstance(channel_data, dict):
                        channel_id = channel_data.get('id')
                        channel_status = channel_data.get('status', 'unknown')
                        invite_link = channel_data.get('invite_link', 'No link')
                        last_updated = channel_data.get('last_updated', 'Never')
                        
                        # Try to get channel title
                        try:
                            chat = await client.get_chat(channel_id)
                            channel_title = chat.title
                        except Exception:
                            channel_title = f"Channel {str(channel_id)[-4:]}"
                        
                        # Format status with emoji
                        status_emoji = "✅" if channel_status == "active" else "❌"
                        
                        channels_text += (
                            f"{i}. <b>{channel_title}</b>\n"
                            f"   📋 <code>{channel_id}</code>\n"
                            f"   🔗 <a href='{invite_link}'>Invite Link</a>\n"
                            f"   {status_emoji} Status: {channel_status}\n"
                            f"   🕐 Updated: {last_updated[:19] if last_updated != 'Never' else 'Never'}\n\n"
                        )
                    else:
                        # Old format - just channel ID
                        channel_id = channel_data
                        try:
                            chat = await client.get_chat(channel_id)
                            channels_text += f"{i}. <code>{channel_id}</code> - {chat.title}\n"
                        except Exception:
                            channels_text += f"{i}. <code>{channel_id}</code> - ᴇʀʀᴏʀ ɢᴇᴛᴛɪɴɢ ɪɴғᴏ\n"
                except Exception as e:
                    channels_text += f"{i}. ❌ Error processing channel data\n"
            channels_text += "\n"
        else:
            channels_text += "<b>🔒 ғᴏʀᴄᴇ sᴜʙsᴄʀɪᴘᴛɪᴏɴ ᴄʜᴀɴɴᴇʟs:</b> ɴᴏɴᴇ\n\n"
        
        # Show request subscription channels
        if request_channels:
            channels_text += "<b>📝 ʀᴇǫᴜᴇsᴛ sᴜʙsᴄʀɪᴘᴛɪᴏɴ ᴄʜᴀɴɴᴇʟs:</b>\n"
            for i, channel_data in enumerate(request_channels, 1):
                try:
                    if isinstance(channel_data, dict):
                        channel_id = channel_data.get('id')
                        channel_status = channel_data.get('status', 'unknown')
                        invite_link = channel_data.get('invite_link', 'No link')
                        last_updated = channel_data.get('last_updated', 'Never')
                        
                        # Try to get channel title
                        try:
                            chat = await client.get_chat(channel_id)
                            channel_title = chat.title
                        except Exception:
                            channel_title = f"Channel {str(channel_id)[-4:]}"
                        
                        # Format status with emoji
                        status_emoji = "✅" if channel_status == "active" else "❌"
                        
                        channels_text += (
                            f"{i}. <b>{channel_title}</b>\n"
                            f"   📋 <code>{channel_id}</code>\n"
                            f"   🔗 <a href='{invite_link}'>Invite Link</a>\n"
                            f"   {status_emoji} Status: {channel_status}\n"
                            f"   🕐 Updated: {last_updated[:19] if last_updated != 'Never' else 'Never'}\n\n"
                        )
                    else:
                        # Old format - just channel ID
                        channel_id = channel_data
                        try:
                            chat = await client.get_chat(channel_id)
                            channels_text += f"{i}. <code>{channel_id}</code> - {chat.title}\n"
                        except Exception:
                            channels_text += f"{i}. <code>{channel_id}</code> - ᴇʀʀᴏʀ ɢᴇᴛᴛɪɴɢ ɪɴғᴏ\n"
                except Exception as e:
                    channels_text += f"{i}. ❌ Error processing channel data\n"
            channels_text += "\n"
        else:
            channels_text += "<b>📝 ʀᴇǫᴜᴇsᴛ sᴜʙsᴄʀɪᴘᴛɪᴏɴ ᴄʜᴀɴɴᴇʟs:</b> ɴᴏɴᴇ\n\n"
        
        channels_text += (
            "<b>💡 ᴄᴏᴍᴍᴀɴᴅs:</b>\n"
            "• <code>/addchannel force [channel_id]</code>\n"
            "• <code>/addchannel request [channel_id]</code>\n"
            "• <code>/removechannel force [channel_id]</code>\n"
            "• <code>/removechannel request [channel_id]</code>\n"
            "• <code>/refreshchannels</code> - Refresh channel links"
        )
        
        await message.reply_text(channels_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        
    except Exception as e:
        await message.reply_text("❌ <b>ᴇʀʀᴏʀ sʜᴏᴡɪɴɢ ᴄʜᴀɴɴᴇʟs!</b>", parse_mode=ParseMode.HTML)
        print(f"❌ Error in show_channels_command: {e}")

@Client.on_message(filters.command("refreshchannels") & filters.private)
async def refresh_channels_command(client: Client, message: Message):
    """Refresh channel invite links manually"""
    try:
        user_id = message.from_user.id
        
        # Check if user is admin
        if not await check_admin(client, message.from_user, message):
            await message.reply_text("❌ <b>ᴜɴᴀᴜᴛʜᴏʀɪᴢᴇᴅ!</b>", parse_mode=ParseMode.HTML)
            return
        
        status_msg = await message.reply_text("🔄 <b>ʀᴇғʀᴇsʜɪɴɢ ᴄʜᴀɴɴᴇʟ ʟɪɴᴋs...</b>", parse_mode=ParseMode.HTML)
        
        # Get current settings
        settings = await get_settings()
        force_channels = settings.get("FORCE_SUB_CHANNELS", [])
        request_channels = settings.get("REQUEST_SUB_CHANNELS", [])
        
        updated = False
        force_updated = 0
        request_updated = 0
        force_errors = 0
        request_errors = 0
        
        # Refresh force channels
        for i, channel_data in enumerate(force_channels):
            try:
                if isinstance(channel_data, dict):
                    channel_id = channel_data.get('id')
                else:
                    # Convert old format
                    channel_id = channel_data
                    force_channels[i] = {
                        'id': channel_id,
                        'invite_link': None,
                        'status': 'active',
                        'last_updated': datetime.now().isoformat()
                    }
                    channel_data = force_channels[i]
                    updated = True
                
                # Try to get/refresh invite link
                try:
                    chat = await client.get_chat(channel_id)
                    invite_link = chat.invite_link or await client.export_chat_invite_link(channel_id)
                    
                    if invite_link != channel_data.get('invite_link'):
                        channel_data['invite_link'] = invite_link
                        channel_data['status'] = 'active'
                        channel_data['last_updated'] = datetime.now().isoformat()
                        channel_data['title'] = chat.title  # Store title for future use
                        updated = True
                        force_updated += 1
                        
                except Exception as e:
                    # Create fallback link
                    if isinstance(channel_id, str) and channel_id.startswith('@'):
                        fallback_link = f"https://t.me/{channel_id[1:]}"
                    else:
                        clean_id = str(channel_id).replace('-100', '')
                        fallback_link = f"https://t.me/c/{clean_id}"
                    
                    channel_data['invite_link'] = fallback_link
                    channel_data['status'] = 'error'
                    channel_data['last_updated'] = datetime.now().isoformat()
                    channel_data['error'] = str(e)[:100]
                    updated = True
                    force_errors += 1
                    
            except Exception as e:
                print(f"❌ Error refreshing force channel {i}: {e}")
                force_errors += 1
        
        # Refresh request channels
        for i, channel_data in enumerate(request_channels):
            try:
                if isinstance(channel_data, dict):
                    channel_id = channel_data.get('id')
                else:
                    # Convert old format
                    channel_id = channel_data
                    request_channels[i] = {
                        'id': channel_id,
                        'invite_link': None,
                        'status': 'active',
                        'last_updated': datetime.now().isoformat()
                    }
                    channel_data = request_channels[i]
                    updated = True
                
                # Try to get/refresh request invite link
                try:
                    chat = await client.get_chat(channel_id)
                    link_obj = await client.create_chat_invite_link(channel_id, creates_join_request=True)
                    invite_link = link_obj.invite_link
                    
                    if invite_link != channel_data.get('invite_link'):
                        channel_data['invite_link'] = invite_link
                        channel_data['status'] = 'active'
                        channel_data['last_updated'] = datetime.now().isoformat()
                        channel_data['title'] = chat.title  # Store title for future use
                        updated = True
                        request_updated += 1
                        
                except Exception as e:
                    # Create fallback link
                    if isinstance(channel_id, str) and channel_id.startswith('@'):
                        fallback_link = f"https://t.me/{channel_id[1:]}"
                    else:
                        clean_id = str(channel_id).replace('-100', '')
                        fallback_link = f"https://t.me/c/{clean_id}"
                    
                    channel_data['invite_link'] = fallback_link
                    channel_data['status'] = 'error'
                    channel_data['last_updated'] = datetime.now().isoformat()
                    channel_data['error'] = str(e)[:100]
                    updated = True
                    request_errors += 1
                    
            except Exception as e:
                print(f"❌ Error refreshing request channel {i}: {e}")
                request_errors += 1
        
        # Update settings if changes were made
        if updated:
            settings["FORCE_SUB_CHANNELS"] = force_channels
            settings["REQUEST_SUB_CHANNELS"] = request_channels
            success = await update_settings(settings)
            
            if success:
                result_text = (
                    f"✅ <b>ᴄʜᴀɴɴᴇʟ ʟɪɴᴋs ʀᴇғʀᴇsʜᴇᴅ!</b>\n\n"
                    f"<b>🔒 ғᴏʀᴄᴇ ᴄʜᴀɴɴᴇʟs:</b>\n"
                    f"   ✅ Updated: {force_updated}\n"
                    f"   ❌ Errors: {force_errors}\n\n"
                    f"<b>📝 ʀᴇǫᴜᴇsᴛ ᴄʜᴀɴɴᴇʟs:</b>\n"
                    f"   ✅ Updated: {request_updated}\n"
                    f"   ❌ Errors: {request_errors}"
                )
            else:
                result_text = "❌ <b>ғᴀɪʟᴇᴅ ᴛᴏ sᴀᴠᴇ ᴄʜᴀɴɢᴇs ᴛᴏ ᴅᴀᴛᴀʙᴀsᴇ!</b>"
        else:
            result_text = "ℹ️ <b>ɴᴏ ᴄʜᴀɴɢᴇs ɴᴇᴇᴅᴇᴅ</b>"
        
        await status_msg.edit_text(result_text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        print(f"❌ Error refreshing channel links: {e}")
        return

@Client.on_message(filters.command("clearrequests") & filters.private & filters.create(check_admin))
async def clear_requests_command(client: Client, message: Message):
    """Clear pending join requests (Admin only)"""
    try:
        user_id = message.from_user.id
        
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

@Client.on_message(filters.command("fix_dumps") & filters.create(check_admin))
async def fix_dump_channels(client: Client, message: Message):
    """Fix dump channels by forcing the bot to meet them"""
    status_msg = await message.reply_text(
        "<b>🔄 ғɪxɪɴɢ ᴅᴜᴍᴘ ᴄʜᴀɴɴᴇʟs...</b>",
        parse_mode=ParseMode.HTML
    )
    
    results = []
    
    for i, dump_id in enumerate(DUMP_CHAT_IDS, 1):
        try:
            # Method 1: Try to get chat directly
            try:
                chat = await client.get_chat(dump_id)
                results.append(f"✅ ᴄʜᴀɴɴᴇʟ {i}: ғɪxᴇᴅ ᴠɪᴀ ɢᴇᴛ_ᴄʜᴀᴛ - {chat.title}")
                continue
            except:
                pass
            
            # Method 2: Send test message
            try:
                test_msg = await client.send_message(
                    dump_id,
                    "🔧 ʙᴏᴛ ɪɴɪᴛɪᴀʟɪᴢᴀᴛɪᴏɴ ᴛᴇsᴛ - ᴛʜɪs ᴍᴇssᴀɢᴇ ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ",
                    disable_notification=True
                )
                await test_msg.delete()
                
                chat = await client.get_chat(dump_id)
                results.append(f"✅ ᴄʜᴀɴɴᴇʟ {i}: ғɪxᴇᴅ ᴠɪᴀ ᴛᴇsᴛ ᴍᴇssᴀɢᴇ - {chat.title}")
                continue
            except Exception as e2:
                results.append(f"❌ ᴄʜᴀɴɴᴇʟ {i}: ᴛᴇsᴛ ᴍᴇssᴀɢᴇ ғᴀɪʟᴇᴅ - {str(e2)}")
            
            # Method 3: Try resolve_peer
            try:
                await client.resolve_peer(dump_id)
                chat = await client.get_chat(dump_id)
                results.append(f"✅ ᴄʜᴀɴɴᴇʟ {i}: ғɪxᴇᴅ ᴠɪᴀ ʀᴇsᴏʟᴠᴇ_ᴘᴇᴇʀ - {chat.title}")
                continue
            except Exception as e3:
                results.append(f"❌ ᴄʜᴀɴɴᴇʟ {i}: ʀᴇsᴏʟᴠᴇ ᴘᴇᴇʀ ғᴀɪʟᴇᴅ - {str(e3)}")
                
        except Exception as main_error:
            results.append(f"❌ ᴄʜᴀɴɴᴇʟ {i} ({dump_id}): {str(main_error)}")
    
    result_text = "<b>🔧 ᴅᴜᴍᴘ ᴄʜᴀɴɴᴇʟ ғɪx ʀᴇsᴜʟᴛs:</b>\n\n" + "\n".join(results)
    await status_msg.edit_text(result_text, parse_mode=ParseMode.HTML)

@Client.on_message(filters.command("check_dumps"))
async def check_dump_channels(client: Client, message: Message):
    """Check the status of all dump channels"""
    if not DUMP_CHAT_IDS:
        await message.reply_text(
            "<b>❌ ɴᴏ ᴅᴜᴍᴘ ᴄʜᴀɴɴᴇʟs ᴄᴏɴғɪɢᴜʀᴇᴅ!</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    status_text = "<b>🔍 ᴅᴜᴍᴘ ᴄʜᴀɴɴᴇʟ sᴛᴀᴛᴜs ᴄʜᴇᴄᴋ</b>\n\n"
    
    for i, dump_id in enumerate(DUMP_CHAT_IDS, 1):
        try:
            # Get chat info
            chat_info = await client.get_chat(dump_id)
            chat_title = chat_info.title or "Unknown"
            
            # Check bot membership
            bot_member = await client.get_chat_member(dump_id, client.me.id)
            bot_status = bot_member.status
            
            if bot_status in ["administrator", "creator"]:
                status_emoji = "✅"
                status_desc = f"ᴀᴅᴍɪɴ ({bot_status})"
            elif bot_status == "member":
                status_emoji = "⚠️"
                status_desc = "ᴍᴇᴍʙᴇʀ (ʟɪᴍɪᴛᴇᴅ)"
            else:
                status_emoji = "❌"
                status_desc = f"ʀᴇsᴛʀɪᴄᴛᴇᴅ ({bot_status})"
            
            status_text += (
                f"{status_emoji} <b>ᴄʜᴀɴɴᴇʟ {i}</b>\n"
                f"├ <b>ᴛɪᴛʟᴇ:</b> {chat_title}\n"
                f"├ <b>ɪᴅ:</b> <code>{dump_id}</code>\n"
                f"└ <b>sᴛᴀᴛᴜs:</b> {status_desc}\n\n"
            )
            
        except Exception as e:
            status_text += (
                f"❌ <b>ᴄʜᴀɴɴᴇʟ {i}</b>\n"
                f"├ <b>ɪᴅ:</b> <code>{dump_id}</code>\n"
                f"└ <b>ᴇʀʀᴏʀ:</b> {str(e)}\n\n"
            )
    
    await message.reply_text(status_text, parse_mode=ParseMode.HTML)

@Client.on_message(filters.command("broadcast") & filters.private & filters.create(check_admin))
async def broadcast_command(client: Client, message: Message):
    """Broadcast message to all users (admin only)"""
    try:
        # Get message to broadcast
        if len(message.command) < 2:
            await message.reply_text(
                "<b>📢 ʙʀᴏᴀᴅᴄᴀsᴛ</b>\n\n"
                "<b>ᴜsᴀɢᴇ:</b> <code>/broadcast &lt;message&gt;</code>\n\n"
                "<b>ᴇxᴀᴍᴘʟᴇ:</b>\n"
                "<code>/broadcast Hello everyone! Bot is updated.</code>",
                parse_mode=ParseMode.HTML
            )
            return
        
        broadcast_text = message.text.split(None, 1)[1]
        
        # Get all users from database
        all_users = await get_all_users()
        
        if not all_users:
            await message.reply_text(
                "<b>❌ ɴᴏ ᴜsᴇʀs ғᴏᴜɴᴅ</b>",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Start broadcasting
        status_msg = await message.reply_text(
            f"<b>📢 sᴛᴀʀᴛɪɴɢ ʙʀᴏᴀᴅᴄᴀsᴛ</b>\n\n"
            f"<b>👥 ᴛᴏᴛᴀʟ ᴜsᴇʀs:</b> {len(all_users):,}\n"
            f"<b>📤 sᴇɴᴛ:</b> 0\n"
            f"<b>❌ ғᴀɪʟᴇᴅ:</b> 0\n"
            f"<b>⏳ sᴛᴀᴛᴜs:</b> sᴇɴᴅɪɴɢ...",
            parse_mode=ParseMode.HTML
        )
        
        sent_count = 0
        failed_count = 0
        
        for i, user in enumerate(all_users):
            try:
                user_id = user.get('_id')
                if user_id:
                    await client.send_message(
                        chat_id=user_id,
                        text=f"<b>📢 ʙʀᴏᴀᴅᴄᴀsᴛ ᴍᴇssᴀɢᴇ</b>\n\n{broadcast_text}",
                        parse_mode=ParseMode.HTML
                    )
                    sent_count += 1
                else:
                    failed_count += 1
                    
            except Exception as e:
                failed_count += 1
                print(f"❌ Failed to send broadcast to {user_id}: {e}")
            
            # Update status every 10 messages
            if (i + 1) % 10 == 0:
                try:
                    await status_msg.edit_text(
                        f"<b>📢 ʙʀᴏᴀᴅᴄᴀsᴛɪɴɢ</b>\n\n"
                        f"<b>👥 ᴛᴏᴛᴀʟ ᴜsᴇʀs:</b> {len(all_users):,}\n"
                        f"<b>📤 sᴇɴᴛ:</b> {sent_count:,}\n"
                        f"<b>❌ ғᴀɪʟᴇᴅ:</b> {failed_count:,}\n"
                        f"<b>⏳ ᴘʀᴏɢʀᴇss:</b> {((i + 1) / len(all_users) * 100):.1f}%",
                        parse_mode=ParseMode.HTML
                    )
                except:
                    pass
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.05)
        
        # Final status
        await status_msg.edit_text(
            f"<b>✅ ʙʀᴏᴀᴅᴄᴀsᴛ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!</b>\n\n"
            f"<b>👥 ᴛᴏᴛᴀʟ ᴜsᴇʀs:</b> {len(all_users):,}\n"
            f"<b>📤 sᴇɴᴛ:</b> {sent_count:,}\n"
            f"<b>❌ ғᴀɪʟᴇᴅ:</b> {failed_count:,}\n"
            f"<b>📊 sᴜᴄᴄᴇss ʀᴀᴛᴇ:</b> {(sent_count / len(all_users) * 100):.1f}%",
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        print(f"❌ Error in broadcast command: {e}")
        await message.reply_text(
            "<b>❌ ᴇʀʀᴏʀ ᴅᴜʀɪɴɢ ʙʀᴏᴀᴅᴄᴀsᴛ</b>",
            parse_mode=ParseMode.HTML
        )

@Client.on_message(filters.command("watermark") & filters.private & filters.create(check_admin))
async def watermark_command(client: Client, message: Message):
    """Manage watermark settings (admin only)"""
    try:
        args = message.text.split()[1:] if len(message.text.split()) > 1 else []
        
        if not args:
            # Show current settings
            settings = await get_watermark_settings()
            
            settings_text = (
                "<b>🎨 ᴡᴀᴛᴇʀᴍᴀʀᴋ sᴇᴛᴛɪɴɢs</b>\n\n"
                f"<b>📊 sᴛᴀᴛᴜs:</b> {'✅ ᴇɴᴀʙʟᴇᴅ' if settings.get('enabled') else '❌ ᴅɪsᴀʙʟᴇᴅ'}\n"
                f"<b>📝 ᴛᴇxᴛ:</b> {settings.get('text', 'N/A')}\n"
                f"<b>📍 ᴘᴏsɪᴛɪᴏɴ:</b> {settings.get('position', 'N/A')}\n"
                f"<b>📏 ғᴏɴᴛ sɪᴢᴇ:</b> {settings.get('font_size', 'N/A')}\n"
                f"<b>🎨 ᴄᴏʟᴏʀ:</b> {settings.get('color', 'N/A')}\n\n"
                "<b>💡 ᴄᴏᴍᴍᴀɴᴅs:</b>\n"
                "• <code>/watermark on/off</code> - ᴛᴏɢɢʟᴇ\n"
                "• <code>/watermark text &lt;text&gt;</code> - sᴇᴛ ᴛᴇxᴛ\n"
                "• <code>/watermark position &lt;pos&gt;</code> - sᴇᴛ ᴘᴏsɪᴛɪᴏɴ\n"
                "• <code>/watermark size &lt;size&gt;</code> - sᴇᴛ sɪᴢᴇ"
            )
            
            await message.reply_text(settings_text, parse_mode=ParseMode.HTML)
            return
        
        command = args[0].lower()
        
        if command in ['on', 'enable']:
            await update_watermark_settings({'enabled': True})
            await message.reply_text("<b>✅ ᴡᴀᴛᴇʀᴍᴀʀᴋ ᴇɴᴀʙʟᴇᴅ!</b>", parse_mode=ParseMode.HTML)
            
        elif command in ['off', 'disable']:
            await update_watermark_settings({'enabled': False})
            await message.reply_text("<b>❌ ᴡᴀᴛᴇʀᴍᴀʀᴋ ᴅɪsᴀʙʟᴇᴅ!</b>", parse_mode=ParseMode.HTML)
            
        elif command == 'text' and len(args) > 1:
            new_text = ' '.join(args[1:])
            await update_watermark_settings({'text': new_text})
            await message.reply_text(f"<b>✅ ᴡᴀᴛᴇʀᴍᴀʀᴋ ᴛᴇxᴛ sᴇᴛ ᴛᴏ:</b> {new_text}", parse_mode=ParseMode.HTML)
            
        elif command == 'position' and len(args) > 1:
            position = args[1].lower()
            valid_positions = ['top-left', 'top-right', 'bottom-left', 'bottom-right', 'center', 'top-center', 'bottom-center']
            
            if position in valid_positions:
                await update_watermark_settings({'position': position})
                await message.reply_text(f"<b>✅ ᴡᴀᴛᴇʀᴍᴀʀᴋ ᴘᴏsɪᴛɪᴏɴ sᴇᴛ ᴛᴏ:</b> {position}", parse_mode=ParseMode.HTML)
            else:
                await message.reply_text(f"<b>❌ ɪɴᴠᴀʟɪᴅ ᴘᴏsɪᴛɪᴏɴ!</b>\n\nᴠᴀʟɪᴅ: {', '.join(valid_positions)}", parse_mode=ParseMode.HTML)
                
        elif command == 'size' and len(args) > 1:
            try:
                size = int(args[1])
                if 12 <= size <= 72:
                    await update_watermark_settings({'font_size': size})
                    await message.reply_text(f"<b>✅ ᴡᴀᴛᴇʀᴍᴀʀᴋ sɪᴢᴇ sᴇᴛ ᴛᴏ:</b> {size}", parse_mode=ParseMode.HTML)
                else:
                    await message.reply_text("<b>❌ sɪᴢᴇ ᴍᴜsᴛ ʙᴇ ʙᴇᴛᴡᴇᴇɴ 12-72!</b>", parse_mode=ParseMode.HTML)
            except ValueError:
                await message.reply_text("<b>❌ ɪɴᴠᴀʟɪᴅ sɪᴢᴇ ɴᴜᴍʙᴇʀ!</b>", parse_mode=ParseMode.HTML)
        else:
            await message.reply_text("<b>❌ ɪɴᴠᴀʟɪᴅ ᴄᴏᴍᴍᴀɴᴅ!</b>\n\nᴜsᴇ <code>/watermark</code> ᴛᴏ sᴇᴇ ᴀᴠᴀɪʟᴀʙʟᴇ ᴏᴘᴛɪᴏɴs.", parse_mode=ParseMode.HTML)
        
    except Exception as e:
        print(f"❌ Error in watermark command: {e}")
        await message.reply_text("<b>❌ ᴇʀʀᴏʀ ᴍᴀɴᴀɢɪɴɢ ᴡᴀᴛᴇʀᴍᴀʀᴋ sᴇᴛᴛɪɴɢs!</b>", parse_mode=ParseMode.HTML)

@Client.on_message(filters.command("cleanup") & filters.private & filters.create(check_admin))
async def cleanup_command(client: Client, message: Message):
    """Clean up temporary files and reset active downloads"""
    try:
        status_msg = await message.reply_text(
            "<b>🧹 ᴄʟᴇᴀɴɪɴɢ ᴜᴘ...</b>",
            parse_mode=ParseMode.HTML
        )
        
        cleaned_files = 0
        cleaned_dirs = 0
        
        # Clean downloads directory
        downloads_dir = "./downloads/"
        if os.path.exists(downloads_dir):
            for item in os.listdir(downloads_dir):
                item_path = os.path.join(downloads_dir, item)
                try:
                    if os.path.isfile(item_path):
                        os.remove(item_path)
                        cleaned_files += 1
                    elif os.path.isdir(item_path):
                        import shutil
                        shutil.rmtree(item_path)
                        cleaned_dirs += 1
                except Exception as e:
                    print(f"❌ Error cleaning {item_path}: {e}")
        
        # Clear active downloads
        active_count = len(active_downloads)
        active_downloads.clear()
        
        # Clean thumbnail files
        thumb_files = 0
        for root, dirs, files in os.walk("."):
            for file in files:
                if file.startswith("thumb_") and file.endswith(".jpg"):
                    try:
                        os.remove(os.path.join(root, file))
                        thumb_files += 1
                    except:
                        pass
        
        await status_msg.edit_text(
            f"<b>✅ ᴄʟᴇᴀɴᴜᴘ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!</b>\n\n"
            f"<b>📁 ғɪʟᴇs ʀᴇᴍᴏᴠᴇᴅ:</b> {cleaned_files}\n"
            f"<b>📂 ᴅɪʀᴇᴄᴛᴏʀɪᴇs ʀᴇᴍᴏᴠᴇᴅ:</b> {cleaned_dirs}\n"
            f"<b>🖼️ ᴛʜᴜᴍʙɴᴀɪʟs ʀᴇᴍᴏᴠᴇᴅ:</b> {thumb_files}\n"
            f"<b>🔄 ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅs ᴄʟᴇᴀʀᴇᴅ:</b> {active_count}",
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        print(f"❌ Error in cleanup command: {e}")
        await message.reply_text(
            f"<b>❌ ᴄʟᴇᴀɴᴜᴘ ᴇʀʀᴏʀ:</b> <code>{str(e)}</code>",
            parse_mode=ParseMode.HTML
        )

@Client.on_message(filters.command("restart") & filters.private & filters.create(check_admin))
async def restart_command(client: Client, message: Message):
    """Restart the bot (admin only)"""
    try:
        await message.reply_text(
            "<b>🔄 ʀᴇsᴛᴀʀᴛɪɴɢ ʙᴏᴛ...</b>\n\n"
            "<i>ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ ᴀ ғᴇᴡ sᴇᴄᴏɴᴅs...</i>",
            parse_mode=ParseMode.HTML
        )
        
        # Clear active downloads
        active_downloads.clear()
        
        # Clean up files
        cleanup_files("./downloads/")
        
        # Restart the bot
        os.execv(sys.executable, ['python'] + sys.argv)
        
    except Exception as e:
        print(f"❌ Error in restart command: {e}")
        await message.reply_text(
            f"<b>❌ ʀᴇsᴛᴀʀᴛ ᴇʀʀᴏʀ:</b> <code>{str(e)}</code>",
            parse_mode=ParseMode.HTML
        )


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
            f"🤖 <blockquote><b>ɪ'ᴍ {Config.BOT_NAME}</b></blockquote>\n\n"
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
            photo=Config.FORCE_PIC,
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



@Client.on_message(filters.command("help") & filters.private)
async def help_command(client: Client, message: Message):
    """Show help message"""
    try:
        user_id = message.from_user.id
        
        if user_id in Config.ADMINS:
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


@Client.on_message(filters.command("stats") & filters.private)
async def stats_command(client: Client, message: Message):
    """Handle /stats command with database integration"""
    try:
        if message.from_user.id not in Config.ADMINS:
            await message.reply_text("🖕")
            return

        # Get stats from database
        stats = await get_stats()
        user_count = await get_user_count()
        
        # Calculate total active downloads across all users
        total_active = sum(len(downloads) for downloads in active_downloads.values())
        
        stats_text = (
            "<b>📊 ʙᴏᴛ sᴛᴀᴛɪsᴛɪᴄs</b>\n\n"
            f"<b>🤖 ʙᴏᴛ ɴᴀᴍᴇ:</b> {Config.BOT_NAME}\n"
            f"<b>👥 ᴛᴏᴛᴀʟ ᴜsᴇʀs:</b> {user_count:,}\n"
            f"<b>📥 ᴛᴏᴛᴀʟ ᴅᴏᴡɴʟᴏᴀᴅs:</b> {stats.get('total_downloads', 0):,}\n"
            f"<b>🔄 ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅs:</b> {total_active}\n"
            f"<b>👤 ᴀᴄᴛɪᴠᴇ ᴜsᴇʀs:</b> {len(active_downloads)}\n"
        )
        
        # Show top sites if available - fix the sorting issue
        sites = stats.get('sites', {})
        if sites and isinstance(sites, dict):
            try:
                # Convert to list of tuples and sort by count (value)
                sites_list = [(site, count) for site, count in sites.items() if isinstance(count, (int, float))]
                top_sites = sorted(sites_list, key=lambda x: x[1], reverse=True)[:3]
                
                if top_sites:
                    stats_text += "<b>🌐 ᴛᴏᴘ sɪᴛᴇs:</b>\n"
                    for site, count in top_sites:
                        stats_text += f"• {site}: {count:,}\n"
                    stats_text += "\n"
            except Exception as e:
                print(f"Error processing sites: {e}")
        
        stats_text += "<b>✅ sᴛᴀᴛᴜs:</b> ʙᴏᴛ ɪs ᴡᴏʀᴋɪɴɢ!"
        
        await message.reply_text(stats_text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        print(f"❌ Error in stats command: {e}")
        import traceback
        traceback.print_exc()
        await message.reply_text(
            "<b>❌ ᴇʀʀᴏʀ ʟᴏᴀᴅɪɴɢ sᴛᴀᴛɪsᴛɪᴄs</b>",
            parse_mode=ParseMode.HTML
        )

async def get_user_rank(user_id: int):
    try:
        user = await get_user(user_id)
        user_downloads = user.get('total_downloads', 0)
        
        higher_users = await user_data.count_documents({
            'total_downloads': {'$gt': user_downloads}
        })
        
        return higher_users + 1
    except Exception as e:
        logging.error(f"Error getting user rank for {user_id}: {e}")
        return 0

async def get_user_download_history(user_id: int, limit: int = 10):
    try:
        history = []
        async for entry in download_history.find({'user_id': user_id}).sort('download_time', -1).limit(limit):
            history.append(entry)
        return history
    except Exception as e:
        logging.error(f"Error getting download history for user {user_id}: {e}")
        return []
    
def get_active_download_count(user_id):
    """Get number of active downloads for a user"""
    return len(active_downloads.get(user_id, []))

@Client.on_message(filters.command("mystats") & filters.private)
async def mystats_command(client: Client, message: Message):
    """Show user's personal statistics"""
    try:
        user_id = message.from_user.id
        username = message.from_user.first_name or message.from_user.username or "Unknown"
        
        # Register/update user
        await register_new_user(user_id, username, message.from_user.first_name or "")
        
        # Get user data from database
        user = await get_user(user_id)
        user_rank = await get_user_rank(user_id)
        
        # Get user's download history
        history = await get_user_download_history(user_id, 5)
        
        # Get current active downloads
        current_downloads = get_active_download_count(user_id)
        
        mystats_text = f"<b>📊 ʏᴏᴜʀ sᴛᴀᴛɪsᴛɪᴄs</b>\n\n"
        mystats_text += f"<b>👤 ɴᴀᴍᴇ:</b> {username}\n"
        mystats_text += f"<b>🆔 ᴜsᴇʀ ɪᴅ:</b> <code>{user_id}</code>\n"
        mystats_text += f"<b>📥 ᴛᴏᴛᴀʟ ᴅᴏᴡɴʟᴏᴀᴅs:</b> {user.get('total_downloads', 0):,}\n"
        mystats_text += f"<b>💾 ᴛᴏᴛᴀʟ sɪᴢᴇ:</b> {format_bytes(user.get('total_size', 0))}\n"
        mystats_text += f"<b>🔄 ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅs:</b> {current_downloads}\n"
        mystats_text += f"<b>🏆 ʀᴀɴᴋ:</b> #{user_rank}\n"
        mystats_text += f"<b>📅 ᴊᴏɪɴᴇᴅ:</b> {user.get('join_date', datetime.now()).strftime('%Y-%m-%d')}\n\n"
        
        # Show favorite sites - fix the sorting issue
        favorite_sites = user.get('favorite_sites', {})
        if favorite_sites and isinstance(favorite_sites, dict):
            try:
                # Convert to list of tuples and sort by count (value)
                sites_list = [(site, count) for site, count in favorite_sites.items() if isinstance(count, (int, float))]
                top_sites = sorted(sites_list, key=lambda x: x[1], reverse=True)[:3]
                
                if top_sites:
                    mystats_text += "<b>🌐 ғᴀᴠᴏʀɪᴛᴇ sɪᴛᴇs:</b>\n"
                    for site, count in top_sites:
                        mystats_text += f"• {site}: {count:,}\n"
                    mystats_text += "\n"
            except Exception as e:
                print(f"Error processing favorite sites: {e}")
        
        # Show recent downloads
        if history:
            mystats_text += "<b>📋 ʀᴇᴄᴇɴᴛ ᴅᴏᴡɴʟᴏᴀᴅs:</b>\n"
            for item in history[:3]:
                date = item.get('download_time', datetime.now()).strftime('%m-%d')
                site = item.get('site', 'Unknown')
                mystats_text += f"• {date} - {site}\n"
        
        await message.reply_text(mystats_text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        print(f"❌ Error in mystats command: {e}")
        import traceback
        traceback.print_exc()
        await message.reply_text(
            "<b>❌ ᴇʀʀᴏʀ ʟᴏᴀᴅɪɴɢ ʏᴏᴜʀ sᴛᴀᴛɪsᴛɪᴄs</b>",
            parse_mode=ParseMode.HTML
        )