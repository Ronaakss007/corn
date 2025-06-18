import os
import re
import time
import asyncio
import yt_dlp
import aiohttp
import aiofiles
import json
import logging
from datetime import datetime
from collections import defaultdict, Counter
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode
from config import Config
from pyrogram import Client
from pyrogram.errors import FloodWait
import math
import sys
# Add this import
from commands.basic import check_subscription
from database import *
from helper_func import *

# Import admin conversations - ADD THIS LINE
try:
    from commands.admin_cb import admin_conversations
except ImportError:
    admin_conversations = {}

user_client = None

# Get dump channels from config (fixed)
DUMP_CHAT_IDS = Config.DUMP_CHAT_IDS

# Global variables to track downloads
active_downloads = {}

class ProgressTracker:
    def __init__(self):
        self.start_time = time.time()
        self.downloaded = 0
        self.total_size = 0
        self.speed = 0
        self.eta = 0
        self.status = "sᴛᴀʀᴛɪɴɢ..."
        self.filename = ""
        self.metadata = {}
        self.upload_progress = 0
        self.upload_total = 0

# Create a custom filter function
def not_in_admin_conversation(_, __, message):
    """Filter to exclude users in admin conversations"""
    try:
        user_id = message.from_user.id
        is_in_conversation = user_id in admin_conversations
        print(f"🔍 Filter check: User {user_id} in admin conversation: {is_in_conversation}")
        return not is_in_conversation
    except Exception as e:
        print(f"❌ Error in admin conversation filter: {e}")
        return True  # Allow message if filter fails
from admin_state import admin_conversations
def not_admin_user(_, __, message):
    """Check if user is not an admin"""
    from helper_func import check_admin
    return not check_admin(None, message.from_user)

@Client.on_message(filters.private & filters.text & ~filters.command([
    "start", "ping", "help", "stats", "mystats", "leaderboard", "history", "cancel",
    "fix_dumps", "check_dumps", "force_meet", "reset_stats", "broadcast", 
    "watermark", "logs", "cleanup", "restart", "test", "files", "admin", "addchannel",
    "refresh", "showchannels", "removechannel", "refreshchannels"
]), group=10)
async def handle_url_message(client: Client, message: Message):
    """Handle URL messages for download - Admin-friendly version"""
    try:
        from config import Config
        from admin_state import admin_conversations, has_admin_conversation
        
        user_id = message.from_user.id
        
        # Add production debugging
        print(f"🔗 [PROD] Download handler called for user {user_id}")
        print(f"📊 [PROD] Admin conversations: {list(admin_conversations.keys())}")
        print(f"👤 [PROD] User is admin: {user_id in Config.ADMINS}")
        
        # Check if message exists
        if not message.text:
            print(f"❌ [PROD] No message text for user {user_id}")
            return
            
        text = message.text.strip()
        print(f"💬 [PROD] Message text: {text[:50]}...")
        
        # CRITICAL: Check admin conversation state FIRST before any processing
        if has_admin_conversation(user_id):
            print(f"🛑 [PROD] User {user_id} is in admin conversation state - skipping URL handler completely")
            return
        
        # Alternative check using direct dictionary access
        if user_id in admin_conversations:
            print(f"🛑 [PROD] User {user_id} found in admin_conversations - skipping URL handler")
            return
        
        # Check URL indicators
        url_indicators = ['http://', 'https://', 'www.', 'youtube.com', 'youtu.be', 'instagram.com', 'tiktok.com', 'facebook.com', 'twitter.com', 'x.com']
        
        is_url = any(indicator in text.lower() for indicator in url_indicators)
        
        # If it's not a URL, let other handlers process it
        if not is_url:
            print(f"📝 [PROD] Text from user {user_id} is not a URL - letting other handlers process")
            return
        
        # Additional check: if it's a telegram link, it might be admin setting button URL
        if 't.me/' in text.lower() and user_id in Config.ADMINS:
            print(f"⚠️ [PROD] Admin {user_id} sent t.me link - might be setting button URL, double-checking admin state")
            # Give admin conversation handler priority for t.me links
            await asyncio.sleep(0.2)  # Increased delay for production
            if has_admin_conversation(user_id):
                print(f"🛑 [PROD] Confirmed: Admin {user_id} is in conversation - skipping download")
                return
            # Double check again
            if user_id in admin_conversations:
                print(f"🛑 [PROD] Double-check: Admin {user_id} is in conversation - skipping download")
                return
        
        # If user is admin and sent a URL, process it
        if user_id in Config.ADMINS:
            print(f"🔗 [PROD] Admin {user_id} sent URL: {text[:50]}... - Processing download")
        else:
            # Check subscription for non-admins
            if not await check_subscription(client, message):
                return
        
        url = text.strip()
        
        # Enhanced URL validation - but skip validation for t.me links that might be button URLs
        if not (url.startswith(('http://', 'https://')) or any(site in url.lower() for site in ['youtube.com', 'youtu.be', 'instagram.com', 'tiktok.com', 'facebook.com', 'twitter.com', 'x.com'])):
            await message.reply_text(
                "<b>❌ ɪɴᴠᴀʟɪᴅ ᴜʀʟ</b>\n\n"
                "ᴘʟᴇᴀsᴇ sᴇɴᴅ ᴀ ᴠᴀʟɪᴅ ᴜʀʟ sᴛᴀʀᴛɪɴɢ ᴡɪᴛʜ http:// ᴏʀ https://",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Skip processing t.me links as they're not downloadable
        if 't.me/' in url.lower():
            print(f"⚠️ [PROD] Skipping t.me link as it's not downloadable: {url}")
            return
        
        # Continue with download process...
        print(f"🚀 [PROD] Starting download process for user {user_id}")
        
        # Normalize URL if needed
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        username = message.from_user.first_name or message.from_user.username or "Unknown"
        first_name = message.from_user.first_name or ""
        
        # Register/update user in database
        await register_new_user(user_id, username, first_name)
        
        # Check if user already has active download
        if user_id in active_downloads:
            await message.reply_text(
                "<b>❌ ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅ</b>\n\n"
                "ʏᴏᴜ ᴀʟʀᴇᴀᴅʏ ʜᴀᴠᴇ ᴀɴ ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅ! ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ ғᴏʀ ɪᴛ ᴛᴏ ᴄᴏᴍᴘʟᴇᴛᴇ.",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Start download process
        active_downloads[user_id] = ProgressTracker()
        
        status_msg = await message.reply_text(
            "<b>!</b>",
            parse_mode=ParseMode.HTML
        )
        await status_msg.edit_text("<b>!!</b>")
        await asyncio.sleep(0.3)
        await status_msg.edit_text("<b>!!!</b>")
        
        # Extract metadata and start download
        metadata = await get_video_metadata(url)
        if metadata:
            active_downloads[user_id].metadata = metadata
        
        await download_and_send(client, message, status_msg, url, user_id)
        
    except Exception as e:
        print(f"❌ [PROD] Error in handle_url_message: {e}")
        import traceback
        traceback.print_exc()
        await message.reply_text(
            f"<b>❌ ᴇʀʀᴏʀ</b>\n\n<code>{str(e)}</code>",
            parse_mode=ParseMode.HTML
        )
        if message.from_user.id in active_downloads:
            del active_downloads[message.from_user.id]


# ==================== DOWNLOAD AND SEND ====================

async def download_and_send(client, message, status_msg, url, user_id):
    """Download video and send to user with progress tracking"""
    try:
        download_dir = f"./downloads/{user_id}/"
        os.makedirs(download_dir, exist_ok=True)
        
        progress_tracker = active_downloads[user_id]
        
        def progress_hook(d):
            """Progress hook for yt-dlp"""
            try:
                if d['status'] == 'downloading':
                    progress_tracker.downloaded = d.get('downloaded_bytes', 0)
                    progress_tracker.total_size = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
                    progress_tracker.speed = d.get('speed', 0) or 0
                    progress_tracker.eta = d.get('eta', 0) or 0
                    progress_tracker.filename = d.get('filename', 'Unknown')
                    progress_tracker.status = "ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ"
                elif d['status'] == 'finished':
                    progress_tracker.status = "ᴄᴏᴍᴘʟᴇᴛᴇᴅ"
                    progress_tracker.filename = d.get('filename', 'Unknown')
            except Exception as e:
                print(f"Progress hook error: {e}")
        
        # Configure yt-dlp options
        ydl_opts = get_download_options(url)
        ydl_opts.update({
            'outtmpl': f'{download_dir}%(title)s.%(ext)s',
            'progress_hooks': [progress_hook],
        })
        
        # Start progress update task
        progress_task = asyncio.create_task(update_progress(status_msg, user_id, url))
        
        # Download in a separate thread
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(None, download_video, url, ydl_opts)
        
        # Cancel progress updates
        progress_task.cancel()
        
        if not success:
            await status_msg.edit_text(
                "<b>❌ ᴅᴏᴡɴʟᴏᴀᴅ ғᴀɪʟᴇᴅ!</b>\n\n"
                "ᴛʜᴇ ᴠɪᴅᴇᴏ ᴄᴏᴜʟᴅ ɴᴏᴛ ʙᴇ ᴅᴏᴡɴʟᴏᴀᴅᴇᴅ.",
                parse_mode=ParseMode.HTML
            )
            return
        
        await status_msg.edit_text(
            "<b>✅ ᴅᴏᴡɴʟᴏᴀᴅ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!</b>\n\n"
            "<b>📋 ᴘʀᴇᴘᴀʀɪɴɢ ғɪʟᴇs ғᴏʀ ᴜᴘʟᴏᴀᴅ...</b>",
            parse_mode=ParseMode.HTML
        )
        
        await asyncio.sleep(1)
        
        # Find downloaded files
        downloaded_files = []
        for file in os.listdir(download_dir):
            if os.path.isfile(os.path.join(download_dir, file)):
                downloaded_files.append(os.path.join(download_dir, file))
        
        if not downloaded_files:
            await status_msg.edit_text(
                "<b>❌ ɴᴏ ғɪʟᴇs ғᴏᴜɴᴅ!</b>",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Process each downloaded file
        uploaded_successfully = False
        total_file_size = 0
        uploaded_files = []
        
        for file_path in downloaded_files:
            try:
                file_size = os.path.getsize(file_path)
                file_name = os.path.basename(file_path)
                
                # Check file size
                if file_size > 2 * 1024 * 1024 * 1024:
                    await message.reply_text(
                        f"<b>❌ ғɪʟᴇ ᴛᴏᴏ ʟᴀʀɢᴇ:</b> {file_name}",
                        parse_mode=ParseMode.HTML
                    )
                    continue
                
                print(f"📤 Starting upload: {file_name} ({format_bytes(file_size)})")
                
                # Upload to first dump channel
                dump_message = await upload_to_dump(client, file_path, DUMP_CHAT_IDS[0], progress_tracker, status_msg)
                
                if dump_message:
                    await status_msg.edit_text(
                        f"<b>✅ ᴜᴘʟᴏᴀᴅ sᴜᴄᴄᴇssғᴜʟ!</b>\n\n"
                        f"<b>📁 ғɪʟᴇ:</b> <code>{file_name}</code>\n"
                        f"<b>💾 sɪᴢᴇ:</b> {format_bytes(file_size)}\n"
                        f"<b>📤 ᴄᴏᴘʏɪɴɢ ᴛᴏ ᴏᴛʜᴇʀ ᴄʜᴀɴɴᴇʟs...</b>",
                        parse_mode=ParseMode.HTML
                    )
                    
                    # Copy to other dump channels
                    for dump_id in DUMP_CHAT_IDS[1:]:
                        try:
                            await client.copy_message(
                                chat_id=dump_id,
                                from_chat_id=DUMP_CHAT_IDS[0],
                                message_id=dump_message.id
                            )
                        except Exception as e:
                            print(f"❌ Error copying to dump {dump_id}: {e}")
                    
                    await status_msg.edit_text(
                        f"<b>📤 sᴇɴᴅɪɴɢ ᴛᴏ ʏᴏᴜ...</b>\n\n"
                        f"<b>📁 ғɪʟᴇ:</b> <code>{file_name}</code>",
                        parse_mode=ParseMode.HTML
                    )
                    
                    # Send to user with enhanced settings
                    is_premium = await is_premium_user(message.from_user.id)
                    user_message = await send_file_to_user_enhanced(
                        client, message, dump_message, file_name, file_size, is_premium
                    )
                    
                    if user_message:
                        uploaded_successfully = True
                        total_file_size += file_size
                        uploaded_files.append({
                            'name': file_name,
                            'size': file_size,
                            'path': file_path
                        })
                    
                else:
                    await message.reply_text(
                        f"<b>❌ ғᴀɪʟᴇᴅ ᴛᴏ ᴜᴘʟᴏᴀᴅ:</b> {os.path.basename(file_path)}",
                        parse_mode=ParseMode.HTML
                    )
                
            except Exception as e:
                print(f"❌ Error processing file {file_path}: {e}")
                await message.reply_text(
                    f"<b>❌ ғᴀɪʟᴇᴅ ᴛᴏ sᴇɴᴅ:</b> {os.path.basename(file_path)}",
                    parse_mode=ParseMode.HTML
                )
        
        # Update database stats after successful uploads
        if uploaded_successfully and total_file_size > 0:
            try:
                site_domain = extract_domain(url)
                username = message.from_user.first_name or message.from_user.username or "Unknown"
                
                file_ext = os.path.splitext(uploaded_files[0]['name'])[1].lower()
                if file_ext in ['.mp4', '.mkv', '.avi', '.mov', '.webm']:
                    file_type = 'video'
                elif file_ext in ['.mp3', '.m4a', '.wav', '.flac', '.ogg']:
                    file_type = 'audio'
                else:
                    file_type = 'document'
                
                success = await update_download_stats(user_id, username, url, total_file_size, file_type)
                
                if success:
                    print(f"✅ Stats updated successfully for user {user_id}")
                else:
                    print(f"❌ Failed to update stats for user {user_id}")

            except Exception as e:
                print(f"❌ Error updating download stats: {e}")
        
        # Delete the status message after everything is done
        if uploaded_successfully:
            try:
                await asyncio.sleep(2)
                await status_msg.delete()
            except Exception:
                await status_msg.edit_text(
                    "<b>✅ ᴀʟʟ ᴅᴏɴᴇ!</b>",
                    parse_mode=ParseMode.HTML
                )
        else:
            await status_msg.edit_text(
                "<b>❌ ɴᴏ ғɪʟᴇs ᴜᴘʟᴏᴀᴅᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!</b>",
                parse_mode=ParseMode.HTML
            )
        
    except Exception as e:
        print(f"❌ Error in download_and_send: {e}")
        await status_msg.edit_text(
            f"<b>❌ ᴇʀʀᴏʀ:</b> {str(e)}",
            parse_mode=ParseMode.HTML
        )
    
    finally:
        cleanup_files(f"./downloads/{user_id}/")
        if user_id in active_downloads:
            del active_downloads[user_id]

# ==================== UPLOAD FUNCTIONS ====================

async def upload_to_dump(client, file_path, dump_id, progress_tracker, status_msg):
    """Upload file to dump channel with progress"""
    try:
        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        
        # Check if file needs splitting
        if file_size > 1.98 * 1024 * 1024 * 1024:
            print(f"📦 File too large ({format_bytes(file_size)}), splitting...")
            await status_msg.edit_text(
                f"<b>📦 sᴘʟɪᴛᴛɪɴɢ ʟᴀʀɢᴇ ғɪʟᴇ</b>\n\n"
                f"<b>📁 ғɪʟᴇ:</b> {file_name}\n"
                f"<b>💾 sɪᴢᴇ:</b> {format_bytes(file_size)}\n"
                f"<b>⏳ sᴛᴀᴛᴜs:</b> sᴘʟɪᴛᴛɪɴɢ...",
                parse_mode=ParseMode.HTML
            )
            
            file_chunks = split_file(file_path)
            uploaded_messages = []
            
            for i, chunk_path in enumerate(file_chunks, 1):
                chunk_size = os.path.getsize(chunk_path)
                chunk_name = os.path.basename(chunk_path)
                
                await status_msg.edit_text(
                    f"<b>📤 ᴜᴘʟᴏᴀᴅɪɴɢ ᴘᴀʀᴛ {i}/{len(file_chunks)}</b>\n\n"
                    f"<b>📁 ғɪʟᴇ:</b> {chunk_name}\n"
                    f"<b>💾 sɪᴢᴇ:</b> {format_bytes(chunk_size)}\n"
                    f"<b>⏳ sᴛᴀᴛᴜs:</b> ᴜᴘʟᴏᴀᴅɪɴɢ...",
                    parse_mode=ParseMode.HTML
                )
                
                chunk_msg = await upload_single_file(client, chunk_path, dump_id, progress_tracker, status_msg, i, len(file_chunks))
                if chunk_msg:
                    uploaded_messages.append(chunk_msg)
                
                try:
                    os.remove(chunk_path)
                except:
                    pass
            
            return uploaded_messages[0] if uploaded_messages else None
        else:
            return await upload_single_file(client, file_path, dump_id, progress_tracker, status_msg)
        
    except Exception as e:
        print(f"❌ Error uploading to dump: {e}")
        await status_msg.edit_text(
            f"<b>❌ ᴜᴘʟᴏᴀᴅ ғᴀɪʟᴇᴅ!</b>\n\n"
            f"<b>📁 ғɪʟᴇ:</b> <code>{os.path.basename(file_path)}</code>\n"
            f"<b>❌ ᴇʀʀᴏʀ:</b> <code>{str(e)}</code>",
            parse_mode=ParseMode.HTML
        )
        return None

async def upload_single_file(client, user_id, file_path, dump_id, progress_tracker, status_msg, part_num=None, total_parts=None):
    """Upload a single file with real-time progress tracking"""
    try:
        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        
        # Initialize progress tracking
        last_update = 0
        upload_start_time = time.time()
        
        progress_data = {
            'current': 0,
            'total': file_size,
            'last_update': 0,
            'start_time': upload_start_time,
            'last_uploaded': 0
        }
        
        # Progress update task
        async def update_progress_task():
            while progress_data['current'] < progress_data['total']:
                try:
                    current = progress_data['current']
                    total = progress_data['total']
                    
                    if current == 0:
                        await asyncio.sleep(1)
                        continue
                    
                    now = time.time()
                    total_time = now - progress_data['start_time']
                    avg_speed = current / total_time if total_time > 0 else 0
                    
                    remaining_bytes = total - current
                    eta = remaining_bytes / avg_speed if avg_speed > 0 else 0
                    
                    percentage = (current / total) * 100 if total > 0 else 0
                    progress_bar = create_progress_bar(percentage)
                    
                    if part_num and total_parts:
                        status_text = f"<b>📤 ᴜᴘʟᴏᴀᴅɪɴɢ ᴘᴀʀᴛ {part_num}/{total_parts}</b>\n\n"
                    else:
                        status_text = f"<b>📤 ᴜᴘʟᴏᴀᴅɪɴɢ...</b>\n\n"
                    
                    status_text += (
                        f"<b>📁 ғɪʟᴇ:</b> <code>{file_name}</code>\n"
                        f"<b>💾 sɪᴢᴇ:</b> {format_bytes(file_size)}\n\n"
                        f"<b>📊 ᴘʀᴏɢʀᴇss:</b>\n"
                        f"<code>{progress_bar}</code> <b>{percentage:.1f}%</b>\n\n"
                        f"<b>📤 ᴜᴘʟᴏᴀᴅᴇᴅ:</b> {format_bytes(current)} / {format_bytes(total)}\n"
                        f"<b>📈 ᴀᴠᴇʀᴀɢᴇ sᴘᴇᴇᴅ:</b> {format_bytes(avg_speed)}/s\n"
                        f"<b>⏱️ ᴇᴛᴀ:</b> {format_time(eta)}"
                    )
                    
                    await safe_edit_message(status_msg, status_text, ParseMode.HTML)
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    print(f"Progress update error: {e}")
                    await asyncio.sleep(2)
        
        def upload_progress(current, total):
            progress_data['current'] = current
            progress_data['total'] = total
        
        # Start progress update task
        progress_task = asyncio.create_task(update_progress_task())

        
        # Create caption with metadata - NO INLINE KEYBOARD for dump channels
        metadata = progress_tracker.metadata
        leecher = f"@{message.from_user.username}" if message.from_user.username else (message.from_user.first_name or "Unknown")
        if part_num and total_parts:
            caption = f"<b>{file_name}</b>\n<b>📦 Part {part_num}/{total_parts} | {format_bytes(file_size)}</b>\n\n"
        else:
            caption = f"<b>{file_name}</b>| <b> {format_bytes(file_size)}</b>\n"

        
        
        # Generate thumbnail for videos
        thumbnail_path = None
        if file_path.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm')):
            thumbnail_path = f"{os.path.dirname(file_path)}/thumb_{int(time.time())}.jpg"
            generated_thumb = await generate_thumbnail(file_path, thumbnail_path, 10)
            if not generated_thumb:
                thumbnail_path = None
        
        # Get video dimensions
        width, height = 1280, 720
        if file_path.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm')):
            width, height = await get_video_dimensions(file_path)
        
        # Upload with retry mechanism
        dump_message = None
        
        try:
            if file_path.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm')):
                # Send as video to DUMP CHANNEL - NO KEYBOARD
                dump_message = await client.send_video(
                    chat_id=dump_id,
                    video=file_path,
                    caption=caption,
                    supports_streaming=True,
                    thumb=thumbnail_path,
                    duration=int(metadata.get('duration', 0)) if metadata else 0,
                    width=width,
                    height=height,
                    progress=upload_progress,
                    parse_mode=ParseMode.HTML
                )
            elif file_path.lower().endswith(('.mp3', '.m4a', '.wav', '.flac', '.ogg')):
                # Send as audio to DUMP CHANNEL - NO KEYBOARD
                dump_message = await client.send_audio(
                    chat_id=dump_id,
                    audio=file_path,
                    caption=caption,
                    duration=int(metadata.get('duration', 0)) if metadata else 0,
                    performer=metadata.get('uploader', 'Unknown') if metadata else 'Unknown',
                    title=metadata.get('title', file_name) if metadata else file_name,
                    thumb=thumbnail_path,
                    progress=upload_progress,
                    parse_mode=ParseMode.HTML
                )
            else:
                # Send as document to DUMP CHANNEL - NO KEYBOARD
                dump_message = await client.send_document(
                    chat_id=dump_id,
                    document=file_path,
                    caption=caption,
                    thumb=thumbnail_path,
                    progress=upload_progress,
                    parse_mode=ParseMode.HTML
                )
        
        except Exception as e:
            print(f"❌ Upload failed: {e}")
            raise e
        
        finally:
            # Cancel progress task
            progress_task.cancel()
            
            # Clean up thumbnail
            if thumbnail_path and os.path.exists(thumbnail_path):
                try:
                    os.remove(thumbnail_path)
                except:
                    pass
        
        # Final upload success message
        if dump_message:
            upload_time = time.time() - upload_start_time
            avg_speed = file_size / upload_time if upload_time > 0 else 0
            
            await status_msg.edit_text(
                f"<b>✅ ᴜᴘʟᴏᴀᴅ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!</b>\n\n"
                f"<b>📁 ғɪʟᴇ:</b> <code>{file_name}</code>\n"
                f"<b>💾 sɪᴢᴇ:</b> {format_bytes(file_size)}\n"
                f"<b>⏱️ ᴛɪᴍᴇ ᴛᴀᴋᴇɴ:</b> {format_time(upload_time)}\n"
                f"<b>📈 ᴀᴠᴇʀᴀɢᴇ sᴘᴇᴇᴅ:</b> {format_bytes(avg_speed)}/s",
                parse_mode=ParseMode.HTML
            )
        
        return dump_message
        
    except Exception as e:
        print(f"❌ Error uploading single file: {e}")
        await status_msg.edit_text(
            f"<b>❌ ᴜᴘʟᴏᴀᴅ ғᴀɪʟᴇᴅ!</b>\n\n"
            f"<b>📁 ғɪʟᴇ:</b> <code>{file_name}</code>\n"
            f"<b>❌ ᴇʀʀᴏʀ:</b> <code>{str(e)}</code>",
            parse_mode=ParseMode.HTML
        )
        return None

# ==================== ENHANCED FILE SENDING ====================

# Replace the section around lines 533-570 with this:
async def send_file_to_user_enhanced(client, message, dump_message, file_name, file_size, is_premium):
    """Enhanced file sending with all protection features including spoiler support"""
    try:
        # Get file settings
        settings = await get_file_settings()
        
        protect_content = settings.get('protect_content', False)
        show_caption = settings.get('show_caption', True)
        auto_delete = settings.get('auto_delete', False)
        auto_delete_time = settings.get('auto_delete_time', 300)
        inline_buttons = settings.get('inline_buttons', True)
        spoiler_enabled = settings.get('spoiler_enabled', True)  # New setting
        
        # Create caption if enabled
        caption = None
        if show_caption:
            caption = f"<b>{file_name}</b>\n<b> {format_bytes(file_size)}</b>"
        
        # Create keyboard if enabled
        keyboard = None
        if inline_buttons:
            keyboard = await create_user_keyboard(is_premium)
        
        # Get file info from dump message to determine type
        user_message = None
        
        try:
            # Check what type of media the dump message contains
            if dump_message.video:
                user_message = await client.send_video(
                    chat_id=message.chat.id,
                    video=dump_message.video.file_id,
                    caption=caption,
                    parse_mode=ParseMode.HTML if caption else None,
                    reply_markup=keyboard,
                    protect_content=protect_content,
                    has_spoiler=spoiler_enabled,
                    duration=dump_message.video.duration,
                    width=dump_message.video.width,
                    height=dump_message.video.height,
                    thumb=dump_message.video.thumbs[0].file_id if dump_message.video.thumbs else None,
                    supports_streaming=True
                )
            elif dump_message.document:
                user_message = await client.send_document(
                    chat_id=message.chat.id,
                    document=dump_message.document.file_id,
                    caption=caption,
                    parse_mode=ParseMode.HTML if caption else None,
                    reply_markup=keyboard,
                    protect_content=protect_content,
                    thumb=dump_message.document.thumbs[0].file_id if dump_message.document.thumbs else None
                )
            elif dump_message.audio:
                user_message = await client.send_audio(
                    chat_id=message.chat.id,
                    audio=dump_message.audio.file_id,
                    caption=caption,
                    parse_mode=ParseMode.HTML if caption else None,
                    reply_markup=keyboard,
                    protect_content=protect_content,
                    duration=dump_message.audio.duration,
                    performer=dump_message.audio.performer,
                    title=dump_message.audio.title,
                    thumb=dump_message.audio.thumbs[0].file_id if dump_message.audio.thumbs else None
                )
            elif dump_message.photo:
                user_message = await client.send_photo(
                    chat_id=message.chat.id,
                    photo=dump_message.photo.file_id,
                    caption=caption,
                    parse_mode=ParseMode.HTML if caption else None,
                    reply_markup=keyboard,
                    protect_content=protect_content,
                    has_spoiler=spoiler_enabled
                )
            elif dump_message.animation:
                user_message = await client.send_animation(
                    chat_id=message.chat.id,
                    animation=dump_message.animation.file_id,
                    caption=caption,
                    parse_mode=ParseMode.HTML if caption else None,
                    reply_markup=keyboard,
                    protect_content=protect_content,
                    has_spoiler=spoiler_enabled,
                    duration=dump_message.animation.duration,
                    width=dump_message.animation.width,
                    height=dump_message.animation.height,
                    thumb=dump_message.animation.thumbs[0].file_id if dump_message.animation.thumbs else None
                )
            else:
                # Fallback to copy_message if media type not supported
                print("⚠️ Unknown media type, falling back to copy_message")
                user_message = await client.copy_message(
                    chat_id=message.chat.id,
                    from_chat_id=DUMP_CHAT_IDS[0],
                    message_id=dump_message.id,
                    caption=caption,
                    parse_mode=ParseMode.HTML if caption else None,
                    reply_markup=keyboard,
                    protect_content=protect_content
                )
                
        except Exception as e:
            print(f"❌ Error sending with direct method: {e}")
            # Fallback to copy_message
            user_message = await client.copy_message(
                chat_id=message.chat.id,
                from_chat_id=DUMP_CHAT_IDS[0],
                message_id=dump_message.id,
                caption=caption,
                parse_mode=ParseMode.HTML if caption else None,
                reply_markup=keyboard,
                protect_content=protect_content
            )
        
        # Send separate warning message if auto delete is enabled
        warning_message = None
        if auto_delete and user_message:
            warning_message = await message.reply_text(
                f"<b>⚠️ ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ ᴡᴀʀɴɪɴɢ</b>\n\n"
                f"<b>📁 ғɪʟᴇ:</b> <code>{file_name}</code>\n"
                f"<b>⏰ ᴛʜɪs ғɪʟᴇ ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ɪɴ:</b> {format_time(auto_delete_time)}\n\n"
                f"<i>💡 ᴅᴏᴡɴʟᴏᴀᴅ ɪᴛ ǫᴜɪᴄᴋʟʏ ʙᴇғᴏʀᴇ ɪᴛ's ʀᴇᴍᴏᴠᴇᴅ!</i>",
                parse_mode=ParseMode.HTML
            )
            
            # Schedule auto delete with notification update
            asyncio.create_task(auto_delete_message_with_notification(
                client, 
                message.chat.id, 
                user_message.id, 
                warning_message.id if warning_message else None,
                file_name,
                auto_delete_time
            ))
        
        return user_message
        
    except Exception as e:
        print(f"❌ Error sending enhanced file to user: {e}")
        return None

async def auto_delete_message_with_notification(client, chat_id, file_message_id, warning_message_id, file_name, delay_seconds):
    """Auto delete message after specified time with notification update"""
    try:
        # Wait for the specified delay
        await asyncio.sleep(delay_seconds)
        
        # Delete the file message
        try:
            await client.delete_messages(chat_id, file_message_id)
            print(f"✅ Auto-deleted file message {file_message_id} from chat {chat_id}")
            
            # Update warning message to show deletion notification
            if warning_message_id:
                try:
                    await client.edit_message_text(
                        chat_id=chat_id,
                        message_id=warning_message_id,
                        text=f"<b><blockquote>🗑️ ғɪʟᴇ ᴅᴇʟᴇᴛᴇᴅ</b></blockquote>\n\n"
                             f"<b>📁 ғɪʟᴇ:</b> <code>{file_name}</code>\n"
                             f"<b>⏰ ᴅᴇʟᴇᴛᴇᴅ ᴀᴛ:</b> {datetime.now().strftime('%H:%M:%S')}\n\n"
                             f"<i>💭 ᴛʜɪs ғɪʟᴇ ʜᴀs ʙᴇᴇɴ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ʀᴇᴍᴏᴠᴇᴅ</i>\n"
                             f"<i>🔄 sᴇɴᴅ ᴛʜᴇ ʟɪɴᴋ ᴀɢᴀɪɴ ᴛᴏ ʀᴇ-ᴅᴏᴡɴʟᴏᴀᴅ</i>",
                        parse_mode=ParseMode.HTML
                    )
                    print(f"✅ Updated warning message to deletion notification")
                    
                    
                except Exception as e:
                    print(f"❌ Error updating warning message: {e}")
                    
        except Exception as e:
            print(f"❌ Error deleting file message: {e}")
            
            # If file deletion failed, still update warning message
            if warning_message_id:
                try:
                    await client.edit_message_text(
                        chat_id=chat_id,
                        message_id=warning_message_id,
                        text=f"<b>❌ ᴅᴇʟᴇᴛɪᴏɴ ғᴀɪʟᴇᴅ</b>\n\n"
                             f"<b>📁 ғɪʟᴇ:</b> <code>{file_name}</code>\n"
                             f"<b>⚠️ ᴄᴏᴜʟᴅ ɴᴏᴛ ᴀᴜᴛᴏ-ᴅᴇʟᴇᴛᴇ ᴛʜɪs ғɪʟᴇ</b>\n\n"
                             f"<i>💡 ᴘʟᴇᴀsᴇ ᴅᴇʟᴇᴛᴇ ɪᴛ ᴍᴀɴᴜᴀʟʟʏ ɪғ ɴᴇᴇᴅᴇᴅ</i>",
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e2:
                    print(f"❌ Error updating warning message after deletion failure: {e2}")
                    
    except Exception as e:
        print(f"❌ Error in auto delete with notification: {e}")

# Keep the old function for backward compatibility
async def auto_delete_message(client, chat_id, message_id, delay_seconds):
    """Auto delete message after specified time (simple version)"""
    try:
        await asyncio.sleep(delay_seconds)
        await client.delete_messages(chat_id, message_id)
        print(f"✅ Auto-deleted message {message_id} from chat {chat_id}")
    except Exception as e:
        print(f"❌ Error auto-deleting message: {e}")



# ==================== PROGRESS UPDATE ====================

async def update_progress(status_msg, user_id, url):
    """Update progress message every few seconds"""
    try:
        while user_id in active_downloads:
            progress_tracker = active_downloads[user_id]
            
            if progress_tracker.total_size > 0:
                percentage = (progress_tracker.downloaded / progress_tracker.total_size) * 100
                progress_bar = create_progress_bar(percentage)
                
                downloaded_str = format_bytes(progress_tracker.downloaded)
                total_str = format_bytes(progress_tracker.total_size)
                speed_str = format_bytes(progress_tracker.speed) + "/s" if progress_tracker.speed > 0 else "0 ʙ/s"
                eta_str = format_time(progress_tracker.eta) if progress_tracker.eta > 0 else "ᴜɴᴋɴᴏᴡɴ"
                
                progress_text = f"<b>📥 {progress_tracker.status}</b>\n\n"
                progress_text += f"<b>📊 ᴘʀᴏɢʀᴇss:</b>\n"
                progress_text += f"<code>{progress_bar}</code> <b>{percentage:.1f}%</b>\n\n"
                progress_text += f"<b>📦 sɪᴢᴇ:</b> {downloaded_str} / {total_str}\n"
                progress_text += f"<b>⚡ sᴘᴇᴇᴅ:</b> {speed_str}\n"
                progress_text += f"<b>⏱️ ᴇᴛᴀ:</b> {eta_str}\n"
                progress_text += f"<b>📁 ғɪʟᴇ:</b> <code>{os.path.basename(progress_tracker.filename)}</code>"
            else:
                progress_text = f"<b>📥 {progress_tracker.status}</b>\n\n"
                progress_text += f"<b>🔗 ᴜʀʟ:</b> <code>{url}</code>\n"
                progress_text += f"<b>⏳ sᴛᴀᴛᴜs:</b> ᴀɴᴀʟʏᴢɪɴɢ ᴠɪᴅᴇᴏ..."
            
            await safe_edit_message(status_msg, progress_text, ParseMode.HTML)
            await asyncio.sleep(3)
            
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"❌ Progress update error: {e}")

# ==================== DOWNLOAD FUNCTION ====================

def download_video(url, ydl_opts):
    """Download video using yt-dlp with speed optimizations"""
    try:
        import yt_dlp
        from urllib.parse import urlparse
        
        domain = urlparse(url).netloc.lower()
        
        # Speed-optimized options
        speed_opts = {
            **ydl_opts,
            'concurrent_fragment_downloads': 4,
            'retries': 5,
            'fragment_retries': 5,
            'retry_sleep_functions': {
                'http': lambda n: min(2 ** n, 10),
                'fragment': lambda n: min(2 ** n, 5)
            },
            'socket_timeout': 30,
            'http_chunk_size': 1024 * 1024,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            },
            'writesubtitles': False,
            'writeautomaticsub': False,
            'writethumbnail': False,
            'writeinfojson': False,
            'no_check_certificate': True,
            'prefer_insecure': True,
        }
        
        # Site-specific optimizations
        if 'youtube' in domain or 'youtu.be' in domain:
            speed_opts.update({
                'format': 'best[height<=720][protocol^=https]/best[height<=480]/best',
                'extractor_args': {
                    'youtube': {
                        'skip': ['dash'],
                        'player_skip': ['js'],
                    }
                }
            })
        elif 'instagram' in domain:
            speed_opts.update({
                'format': 'best/worst',
                'concurrent_fragment_downloads': 2,
            })
        elif any(adult_site in domain for adult_site in ['pornhub', 'xvideos', 'xnxx', 'xhamster']):
            speed_opts.update({
                'format': 'best[height<=720]/best',
                'concurrent_fragment_downloads': 6,
                'http_headers': {
                    **speed_opts['http_headers'],
                    'Referer': f'https://{domain}/',
                }
            })
        else:
            speed_opts.update({
                'format': 'best/worst',
                'concurrent_fragment_downloads': 3,
            })
        
        print(f"🚀 Starting optimized download from {domain}...")
        
        try:
            with yt_dlp.YoutubeDL(speed_opts) as ydl:
                ydl.download([url])
                print(f"✅ High-speed download successful")
                return True
                
        except Exception as e:
            print(f"❌ High-speed download failed: {e}")
            
            # Fallback with conservative settings
            print(f"🔄 Trying conservative fallback...")
            conservative_opts = {
                **ydl_opts,
                'format': 'worst/best',
                'concurrent_fragment_downloads': 1,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'
                },
                'socket_timeout': 60,
                'retries': 3,
            }
            
            try:
                with yt_dlp.YoutubeDL(conservative_opts) as ydl_conservative:
                    ydl_conservative.download([url])
                    print(f"✅ Conservative download successful")
                    return True
            except Exception as e2:
                print(f"❌ All download attempts failed: {e2}")
                return False
                        
    except Exception as e:
        print(f"❌ Critical download error: {e}")
        return False

print("✅ Download module loaded successfully")
