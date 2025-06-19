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
from commands.basic import check_subscription
from database import *
from helper_func import *
import mimetypes
from pathlib import Path

# Import admin conversations
try:
    from commands.admin_cb import admin_conversations
except ImportError:
    admin_conversations = {}

user_client = None

# Get dump channels from config
DUMP_CHAT_IDS = Config.DUMP_CHAT_IDS

# Global variables to track downloads - Support multiple downloads per user
active_downloads = {}  # user_id: [list of ProgressTracker objects]
MAX_CONCURRENT_DOWNLOADS = 10  # Maximum concurrent downloads per user

class ProgressTracker:
    def __init__(self, url, download_id):
        self.url = url
        self.download_id = download_id
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
        self.status_msg = None

# Create a custom filter function
def not_in_admin_conversation(_, __, message):
    """Filter to exclude users in admin conversations"""
    try:
        user_id = message.from_user.id
        is_in_conversation = user_id in admin_conversations
        return not is_in_conversation
    except Exception as e:
        return True

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
    """Handle URL messages for download - Production version with concurrent support"""
    try:
        from config import Config
        from admin_state import admin_conversations, has_admin_conversation
        
        user_id = message.from_user.id
        
        if not message.text:
            return
            
        text = message.text.strip()
        
        # Check admin conversation state
        if has_admin_conversation(user_id) or user_id in admin_conversations:
            return
        
        # Check URL indicators
        url_indicators = ['http://', 'https://', 'www.', 'youtube.com', 'youtu.be', 'instagram.com', 'tiktok.com', 'facebook.com', 'twitter.com', 'x.com']
        
        is_url = any(indicator in text.lower() for indicator in url_indicators)
        
        if not is_url:
            return
        
        # Skip t.me links for admins (might be setting button URLs)
        if 't.me/' in text.lower() and user_id in Config.ADMINS:
            await asyncio.sleep(0.2)
            if has_admin_conversation(user_id) or user_id in admin_conversations:
                return
        
        # Skip t.me links as they're not downloadable
        if 't.me/' in text.lower():
            return
        
        # Check subscription for non-admins
        if user_id not in Config.ADMINS:
            if not await check_subscription(client, message):
                return
        
        url = text.strip()
        
        # Enhanced URL validation
        if not (url.startswith(('http://', 'https://')) or any(site in url.lower() for site in ['youtube.com', 'youtu.be', 'instagram.com', 'tiktok.com', 'facebook.com', 'twitter.com', 'x.com'])):
            await message.reply_text(
                "<b>❌ ɪɴᴠᴀʟɪᴅ ᴜʀʟ</b>\n\n"
                "ᴘʟᴇᴀsᴇ sᴇɴᴅ ᴀ ᴠᴀʟɪᴅ ᴜʀʟ sᴛᴀʀᴛɪɴɢ ᴡɪᴛʜ http:// ᴏʀ https://",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Normalize URL if needed
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        username = message.from_user.first_name or message.from_user.username or "Unknown"
        first_name = message.from_user.first_name or ""
        
        # Register/update user in database
        await register_new_user(user_id, username, first_name)
        
        # Check concurrent download limit
        if user_id in active_downloads:
            if len(active_downloads[user_id]) >= MAX_CONCURRENT_DOWNLOADS:
                await message.reply_text(
                    f"<b>⚠️ ᴅᴏᴡɴʟᴏᴀᴅ ʟɪᴍɪᴛ ʀᴇᴀᴄʜᴇᴅ</b>\n\n"
                    f"ʏᴏᴜ ᴄᴀɴ ʜᴀᴠᴇ ᴍᴀxɪᴍᴜᴍ <b>{MAX_CONCURRENT_DOWNLOADS}</b> ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅs.\n"
                    f"ᴄᴜʀʀᴇɴᴛ ᴀᴄᴛɪᴠᴇ: <b>{len(active_downloads[user_id])}</b>\n\n"
                    f"ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ ғᴏʀ ᴏɴᴇ ᴛᴏ ᴄᴏᴍᴘʟᴇᴛᴇ.",
                    parse_mode=ParseMode.HTML
                )
                return
        else:
            active_downloads[user_id] = []
        
        # Generate unique download ID
        download_id = f"{user_id}_{int(time.time())}_{len(active_downloads[user_id])}"
        
        # Create progress tracker
        progress_tracker = ProgressTracker(url, download_id)
        active_downloads[user_id].append(progress_tracker)
        
        # Create status message
        status_msg = await message.reply_text("<b>›› ɪɴɪᴛɪᴀʟɪᴢɪɴɢ...</b>", parse_mode=ParseMode.HTML)
        progress_tracker.status_msg = status_msg
        
        # Extract metadata
        metadata = await get_video_metadata(url)
        if metadata:
            progress_tracker.metadata = metadata
        
        # Start download in background
        asyncio.create_task(download_and_send_concurrent(client, message, progress_tracker, user_id))
        
    except Exception as e:
        await message.reply_text(
            f"<b>❌ ᴇʀʀᴏʀ</b>\n\n<code>{str(e)}</code>",
            parse_mode=ParseMode.HTML
        )
        # Clean up on error
        if user_id in active_downloads:
            active_downloads[user_id] = [t for t in active_downloads[user_id] if t.download_id != download_id]
            if not active_downloads[user_id]:
                del active_downloads[user_id]

# ==================== CONCURRENT DOWNLOAD AND SEND ====================

async def download_and_send_concurrent(client, message, progress_tracker, user_id):
    """Download video and send to user with concurrent support"""
    download_id = progress_tracker.download_id
    url = progress_tracker.url
    status_msg = progress_tracker.status_msg
    
    try:
        download_dir = f"./downloads/{download_id}/"
        os.makedirs(download_dir, exist_ok=True)
        print(f"Created download directory: {download_dir}")
        
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
                pass
        
        # Configure yt-dlp options
        try:
            ydl_opts = get_download_options(url)
            ydl_opts.update({
                'outtmpl': f'{download_dir}%(title)s.%(ext)s',
                'progress_hooks': [progress_hook],
            })
            print(f"Configured yt-dlp options for URL: {url}")
        except Exception as opts_error:
            print(f"Error configuring yt-dlp options: {opts_error}")
            await status_msg.edit_text(
                f"<b>❌ ᴄᴏɴғɪɢᴜʀᴀᴛɪᴏɴ ᴇʀʀᴏʀ</b>\n\n"
                f"<b>🔗 ᴜʀʟ:</b> <code>{url[:100]}{'...' if len(url) > 100 else ''}</code>\n"
                f"<b>❌ ᴇʀʀᴏʀ:</b> <code>{str(opts_error)}</code>",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Start progress update task
        progress_task = asyncio.create_task(update_progress_concurrent(progress_tracker))
        
        # Download in a separate thread
        try:
            print(f"Starting download for URL: {url}")
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(None, download_video, url, ydl_opts)
            print(f"Download completed. Success: {success}")
        except Exception as download_error:
            print(f"Download execution error: {download_error}")
            success = False
        
        # Cancel progress updates
        try:
            progress_task.cancel()
            await asyncio.sleep(0.1)
        except Exception as cancel_error:
            print(f"Error cancelling progress task: {cancel_error}")
        
        if not success:
            await status_msg.edit_text(
                "<b>❌ ᴅᴏᴡɴʟᴏᴀᴅ ғᴀɪʟᴇᴅ!</b>\n\n"
                f"<b>🔗 ᴜʀʟ:</b> <code>{url[:100]}{'...' if len(url) > 100 else ''}</code>\n"
                "ᴛʜᴇ ᴠɪᴅᴇᴏ ᴄᴏᴜʟᴅ ɴᴏᴛ ʙᴇ ᴅᴏᴡɴʟᴏᴀᴅᴇᴅ.",
                parse_mode=ParseMode.HTML
            )
            return
        
        await status_msg.edit_text(
            "<b>✅ ᴅᴏᴡɴʟᴏᴀᴅ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!</b>\n\n"
            "<b>📋 ᴘʀᴇᴘᴀʀɪɴɢ ғɪʟᴇs ғᴏʀ ᴜᴘʟᴏᴀᴅ...</b>",
            parse_mode=ParseMode.HTML
        )
        
        # Find downloaded files
        downloaded_files = []
        try:
            if not os.path.exists(download_dir):
                print(f"Download directory does not exist: {download_dir}")
                await status_msg.edit_text(
                    "<b>❌ ᴅᴏᴡɴʟᴏᴀᴅ ᴅɪʀᴇᴄᴛᴏʀʏ ɴᴏᴛ ғᴏᴜɴᴅ!</b>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            for file in os.listdir(download_dir):
                file_path = os.path.join(download_dir, file)
                if os.path.isfile(file_path):
                    downloaded_files.append(file_path)
                    
        except Exception as list_error:
            print(f"Error listing downloaded files: {list_error}")
            await status_msg.edit_text(
                f"<b>❌ ᴇʀʀᴏʀ ʟɪsᴛɪɴɢ ғɪʟᴇs</b>\n\n"
                f"<b>❌ ᴇʀʀᴏʀ:</b> <code>{str(list_error)}</code>",
                parse_mode=ParseMode.HTML
            )
            return
        
        if not downloaded_files:
            await status_msg.edit_text(
                "<b>❌ ɴᴏ ғɪʟᴇs ғᴏᴜɴᴅ!</b>\n\n"
                f"<b>📁 ᴅɪʀᴇᴄᴛᴏʀʏ:</b> <code>{download_dir}</code>",
                parse_mode=ParseMode.HTML
            )
            return
        
        print(f"Found {len(downloaded_files)} files to upload")
        
        # Process each downloaded file
        uploaded_successfully = False
        total_file_size = 0
        uploaded_files = []
        failed_uploads = []

        user_info = {
            'id': message.from_user.id,
            'name': message.from_user.first_name or message.from_user.username or "Gᴇɴɪᴇ"
        }
        
        for file_index, file_path in enumerate(downloaded_files, 1):
            try:
                if not os.path.exists(file_path):
                    error_msg = f"File no longer exists: {file_path}"
                    print(error_msg)
                    failed_uploads.append({
                        'file': os.path.basename(file_path),
                        'error': 'File not found'
                    })
                    continue
                
                file_size = os.path.getsize(file_path)
                file_name = os.path.basename(file_path)
                
                print(f"Processing file {file_index}/{len(downloaded_files)}: {file_name}")
                print(f"File size: {file_size} bytes ({file_size / (1024*1024*1024):.2f} GB)")
                
                # Sanitize filename
                try:
                    sanitized_name = sanitize_filename(file_name)
                    if sanitized_name != file_name:
                        sanitized_path = os.path.join(os.path.dirname(file_path), sanitized_name)
                        try:
                            os.rename(file_path, sanitized_path)
                            file_path = sanitized_path
                            file_name = sanitized_name
                            print(f"Renamed file to: {sanitized_name}")
                        except Exception as rename_error:
                            print(f"Failed to rename file: {rename_error}")
                except Exception as sanitize_error:
                    print(f"Error sanitizing filename: {sanitize_error}")
                
                # Update status for current file
                try:
                    await status_msg.edit_text(
                        f"<b>📤 ᴜᴘʟᴏᴀᴅɪɴɢ ғɪʟᴇ {file_index}/{len(downloaded_files)}</b>\n\n"
                        f"<b>📁 ғɪʟᴇ:</b> <code>{file_name[:50]}{'...' if len(file_name) > 50 else ''}</code>\n"
                        f"<b>💾 sɪᴢᴇ:</b> {format_bytes(file_size)}\n"
                        f"<b>🔄 sᴛᴀᴛᴜs:</b> ᴘʀᴇᴘᴀʀɪɴɢ ᴜᴘʟᴏᴀᴅ...",
                        parse_mode=ParseMode.HTML
                    )
                except Exception as status_error:
                    print(f"Error updating status message: {status_error}")
                
                # Upload to user first
                print(f"Starting upload for: {file_name}")
                user_message = await handle_file_upload(client, message, file_path, progress_tracker)
                
                if user_message:
                    print(f"Successfully uploaded: {file_name}")
                    # Then copy to all dump channels
                    try:
                        await copy_to_dumps(client, user_message, file_name, file_size, user_info)
                        print(f"Successfully copied to dump channels: {file_name}")
                    except Exception as dump_error:
                        print(f"Failed to copy to dump channels: {dump_error}")
                    
                    uploaded_successfully = True
                    total_file_size += file_size
                    uploaded_files.append({
                        'name': file_name,
                        'size': file_size,
                        'path': file_path
                    })
                else:
                    error_msg = f"Upload failed for: {file_name}"
                    print(error_msg)
                    failed_uploads.append({
                        'file': file_name,
                        'error': 'Upload function returned None'
                    })
                
            except Exception as file_error:
                error_msg = f"Error processing file {file_path}: {file_error}"
                print(error_msg)
                import traceback
                traceback.print_exc()
                
                failed_uploads.append({
                    'file': os.path.basename(file_path) if 'file_path' in locals() else 'Unknown',
                    'error': str(file_error)
                })
        
        # Report results
        if uploaded_successfully:
            try:
                await status_msg.delete()
                await message.delete()
            except Exception:
                await status_msg.edit_text(
                    f"<b>✅ ᴜᴘʟᴏᴀᴅ ᴄᴏᴍᴘʟᴇᴛᴇ!</b>\n\n"
                    f"<b>📤 ᴜᴘʟᴏᴀᴅᴇᴅ:</b> {len(uploaded_files)} ғɪʟᴇ(s)",
                    parse_mode=ParseMode.HTML
                )
        else:
            await status_msg.edit_text(
                "<b>❌ ᴀʟʟ ᴜᴘʟᴏᴀᴅs ғᴀɪʟᴇᴅ!</b>",
                parse_mode=ParseMode.HTML
            )
        
        # Update database stats
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
                print(f"Database stats updated: {success}")
            except Exception as db_error:
                print(f"Database update error: {db_error}")
        
    except Exception as main_error:
        print(f"Main error: {main_error}")
        import traceback
        traceback.print_exc()
        
        try:
            await status_msg.edit_text(
                f"<b>❌ ᴄʀɪᴛɪᴄᴀʟ ᴇʀʀᴏʀ</b>\n\n"
                f"<b>❌ ᴇʀʀᴏʀ:</b> <code>{str(main_error)[:300]}</code>",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass
    
    finally:
        # Cleanup
        try:
            if 'download_dir' in locals() and os.path.exists(download_dir):
                cleanup_files(download_dir)
        except Exception as cleanup_error:
            print(f"Cleanup error: {cleanup_error}")
        
        # Remove from active downloads
        try:
            if user_id in active_downloads:
                active_downloads[user_id] = [t for t in active_downloads[user_id] if t.download_id != download_id]
                if not active_downloads[user_id]:
                    del active_downloads[user_id]
        except Exception:
            pass

# ==================== FILE UPLOAD HANDLER ====================
async def handle_file_upload(client, message, file_path, progress_tracker):
    """Handle file upload with splitting support"""
    try:
        if not os.path.exists(file_path):
            print(f"File does not exist: {file_path}")
            return None
            
        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        status_msg = progress_tracker.status_msg
        
        print(f"handle_file_upload called for: {file_name}")
        print(f"File size: {file_size} bytes ({file_size / (1024*1024*1024):.2f} GB)")
        
        # Check if file needs splitting (Telegram limit is 2GB, we use 1.98GB as safety margin)
        MAX_FILE_SIZE = 1.98 * 1024 * 1024 * 1024  # 1.98 GB in bytes
        
        if file_size > MAX_FILE_SIZE:
            print(f"File needs splitting: {file_size} > {MAX_FILE_SIZE}")
            await status_msg.edit_text(
                f"<b>📦 sᴘʟɪᴛᴛɪɴɢ ʟᴀʀɢᴇ ғɪʟᴇ</b>\n\n"
                f"<b>📁 ғɪʟᴇ:</b> {file_name[:50]}{'...' if len(file_name) > 50 else ''}\n"
                f"<b>💾 sɪᴢᴇ:</b> {format_bytes(file_size)}\n"
                f"<b>🔄 sᴛᴀᴛᴜs:</b> ᴘʀᴇᴘᴀʀɪɴɢ ᴛᴏ sᴘʟɪᴛ...",
                parse_mode=ParseMode.HTML
            )
            
            try:
                # Split the file
                if is_video_file(file_path):
                    print("Splitting as video file")
                    try:
                        from helper_func import split_video
                        file_chunks = await split_video(file_path)
                    except ImportError:
                        print("split_video not available, using generic split")
                        file_chunks = await split_file_generic(file_path)
                else:
                    print("Splitting as regular file")
                    file_chunks = await split_file_generic(file_path)
                
                if not file_chunks or len(file_chunks) == 0:
                    print("No chunks returned from splitting")
                    await status_msg.edit_text(
                        f"<b>❌ sᴘʟɪᴛᴛɪɴɢ ғᴀɪʟᴇᴅ</b>\n\n"
                        f"<b>📁 ғɪʟᴇ:</b> {file_name[:50]}{'...' if len(file_name) > 50 else ''}\n"
                        f"<b>❌ ᴇʀʀᴏʀ:</b> ᴄᴏᴜʟᴅ ɴᴏᴛ sᴘʟɪᴛ ғɪʟᴇ",
                        parse_mode=ParseMode.HTML
                    )
                    return None
                
                print(f"File split into {len(file_chunks)} chunks")
                uploaded_messages = []
                
                for i, chunk_path in enumerate(file_chunks, 1):
                    if not os.path.exists(chunk_path):
                        print(f"Chunk {i} does not exist: {chunk_path}")
                        continue
                        
                    chunk_size = os.path.getsize(chunk_path)
                    chunk_name = os.path.basename(chunk_path)
                    
                    print(f"Uploading chunk {i}/{len(file_chunks)}: {chunk_name}")
                    
                    await status_msg.edit_text(
                        f"<b>📤 sᴇɴᴅɪɴɢ ᴘᴀʀᴛ {i}/{len(file_chunks)}</b>\n\n"
                        f"<b>📁 ғɪʟᴇ:</b> {chunk_name[:50]}{'...' if len(chunk_name) > 50 else ''}\n"
                        f"<b>💾 sɪᴢᴇ:</b> {format_bytes(chunk_size)}\n"
                        f"<b>📊 ᴘʀᴏɢʀᴇss:</b> {i}/{len(file_chunks)} ᴘᴀʀᴛs",
                        parse_mode=ParseMode.HTML
                    )
                    
                    chunk_msg = await upload_single_file(client, message, chunk_path, progress_tracker, i, len(file_chunks))
                    if chunk_msg:
                        uploaded_messages.append(chunk_msg)
                        print(f"Successfully uploaded chunk {i}")
                    else:
                        print(f"Failed to upload chunk {i}")
                    
                    # Clean up chunk file after upload
                    try:
                        os.remove(chunk_path)
                        print(f"Cleaned up chunk: {chunk_path}")
                    except Exception as cleanup_error:
                        print(f"Failed to remove chunk {chunk_path}: {cleanup_error}")
                
                # Return the first uploaded message for dump channel copying
                return uploaded_messages[0] if uploaded_messages else None
                
            except Exception as split_error:
                print(f"Splitting error: {split_error}")
                import traceback
                traceback.print_exc()
                await status_msg.edit_text(
                    f"<b>❌ sᴘʟɪᴛᴛɪɴɢ ғᴀɪʟᴇᴅ</b>\n\n"
                    f"<b>📁 ғɪʟᴇ:</b> {file_name[:50]}{'...' if len(file_name) > 50 else ''}\n"
                    f"<b>❌ ᴇʀʀᴏʀ:</b> <code>{str(split_error)[:100]}</code>",
                    parse_mode=ParseMode.HTML
                )
                return None
        else:
            # File is under the limit, upload normally
            print(f"File is under size limit, uploading normally")
            return await upload_single_file(client, message, file_path, progress_tracker)
            
    except Exception as main_error:
        print(f"handle_file_upload main error: {main_error}")
        import traceback
        traceback.print_exc()
        try:
            await status_msg.edit_text(
                f"<b>❌ ᴜᴘʟᴏᴀᴅ ғᴀɪʟᴇᴅ!</b>\n\n"
                f"<b>📁 ғɪʟᴇ:</b> <code>{file_name[:50] if 'file_name' in locals() else 'Unknown'}{'...' if 'file_name' in locals() and len(file_name) > 50 else ''}</code>\n"
                f"<b>❌ ᴇʀʀᴏʀ:</b> <code>{str(main_error)[:200]}</code>",
                parse_mode=ParseMode.HTML
            )
        except Exception as edit_error:
            print(f"Failed to edit status message: {edit_error}")
        return None

# ==================== SINGLE FILE UPLOAD ====================

async def upload_single_file(client, message, file_path, progress_tracker, part_num=None, total_parts=None):
    """Upload single file to user with enhanced features"""
    try:
        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        status_msg = progress_tracker.status_msg
        
        print(f"Uploading single file: {file_name}, Size: {file_size} bytes")
        
        # Get user settings
        try:
            settings = await get_file_settings()
            is_premium = await is_premium_user(message.from_user.id)
        except Exception as settings_error:
            print(f"Error getting user settings: {settings_error}")
            # Use default settings
            settings = {
                'protect_content': False,
                'show_caption': True,
                'auto_delete': False,
                'auto_delete_time': 300,
                'inline_buttons': True,
                'spoiler_enabled': False
            }
            is_premium = False
        
        protect_content = settings.get('protect_content', False)
        show_caption = settings.get('show_caption', True)
        auto_delete = settings.get('auto_delete', False)
        auto_delete_time = settings.get('auto_delete_time', 300)
        inline_buttons = settings.get('inline_buttons', True)
        spoiler_enabled = settings.get('spoiler_enabled', False)
        
        # Create caption
        if part_num and total_parts:
            caption = f"<b>{file_name}</b>\n<b>📦 Part {part_num}/{total_parts} | {format_bytes(file_size)}</b>" if show_caption else None
        else:
            caption = f"<b>{file_name}</b> | <b>{format_bytes(file_size)}</b>" if show_caption else None
        
        try:
            keyboard = await create_user_keyboard(is_premium) if inline_buttons else None
        except Exception as keyboard_error:
            print(f"Error creating keyboard: {keyboard_error}")
            keyboard = None
        
        # Progress tracking
        upload_start_time = time.time()
        progress_data = {
            'current': 0,
            'total': file_size,
            'start_time': upload_start_time
        }
        
        def upload_progress(current, total):
            progress_data['current'] = current
            progress_data['total'] = total
        
        # Start progress update task
        progress_task = asyncio.create_task(update_upload_progress_simple(status_msg, progress_data, file_name, part_num, total_parts))
        
        # Generate thumbnail for videos
        thumbnail_path = None
        if file_path.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm')):
            try:
                thumbnail_path = f"{os.path.dirname(file_path)}/thumb_{int(time.time())}.jpg"
                generated_thumb = await generate_thumbnail(file_path, thumbnail_path, 10)
                if not generated_thumb:
                    thumbnail_path = None
            except Exception as thumb_error:
                print(f"Error generating thumbnail: {thumb_error}")
                thumbnail_path = None
        
        # Get video dimensions
        width, height = 1280, 720
        if file_path.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm')):
            try:
                width, height = await get_video_dimensions(file_path)
            except Exception as dim_error:
                print(f"Error getting video dimensions: {dim_error}")
                width, height = 1280, 720
        
        user_message = None
        metadata = progress_tracker.metadata
        
        try:
            if file_path.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm')):
                # Send as video with spoiler support
                user_message = await client.send_video(
                    chat_id=message.chat.id,
                    video=file_path,
                    caption=caption,
                    supports_streaming=True,
                    thumb=thumbnail_path,
                    duration=int(metadata.get('duration', 0)) if metadata else 0,
                    width=width,
                    height=height,
                    progress=upload_progress,
                    parse_mode=ParseMode.HTML if caption else None,
                    reply_markup=keyboard,
                    protect_content=protect_content,
                    has_spoiler=spoiler_enabled  # Spoiler for videos
                )
            elif file_path.lower().endswith(('.mp3', '.m4a', '.wav', '.flac', '.ogg')):
                # Send as audio
                user_message = await client.send_audio(
                    chat_id=message.chat.id,
                    audio=file_path,
                    caption=caption,
                    duration=int(metadata.get('duration', 0)) if metadata else 0,
                    performer=metadata.get('uploader', 'Unknown') if metadata else 'Unknown',
                    title=metadata.get('title', file_name) if metadata else file_name,
                    thumb=thumbnail_path,
                    progress=upload_progress,
                    parse_mode=ParseMode.HTML if caption else None,
                    reply_markup=keyboard,
                    protect_content=protect_content
                )
            else:
                # Send as document
                user_message = await client.send_document(
                    chat_id=message.chat.id,
                    document=file_path,
                    caption=caption,
                    thumb=thumbnail_path,
                    progress=upload_progress,
                    parse_mode=ParseMode.HTML if caption else None,
                    reply_markup=keyboard,
                    protect_content=protect_content
                )
        
        except Exception as upload_error:
            print(f"Upload error: {upload_error}")
            import traceback
            traceback.print_exc()
            raise upload_error
        
        finally:
            # Cancel progress task
            try:
                progress_task.cancel()
                await asyncio.sleep(0.1)
            except Exception:
                pass
            
            # Clean up thumbnail
            if thumbnail_path and os.path.exists(thumbnail_path):
                try:
                    os.remove(thumbnail_path)
                except Exception as thumb_cleanup_error:
                    print(f"Error cleaning up thumbnail: {thumb_cleanup_error}")
        
        print(f"Successfully uploaded: {file_name}")
        return user_message
        
    except Exception as main_error:
        print(f"upload_single_file error: {main_error}")
        import traceback
        traceback.print_exc()
        try:
            await status_msg.edit_text(
                f"<b>❌ ᴜᴘʟᴏᴀᴅ ғᴀɪʟᴇᴅ!</b>\n\n"
                f"<b>📁 ғɪʟᴇ:</b> <code>{file_name if 'file_name' in locals() else 'Unknown'}</code>\n"
                f"<b>❌ ᴇʀʀᴏʀ:</b> <code>{str(main_error)[:200]}</code>",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass
        return None

# ==================== GENERIC FILE SPLITTING ====================

async def split_file_generic(file_path, max_size=1.95 * 1024 * 1024 * 1024):
    """
    Split any file into parts by size
    """
    try:
        print(f"Starting generic file split for: {file_path}")
        
        if not os.path.exists(file_path):
            print(f"❌ File does not exist: {file_path}")
            return [file_path]
        
        file_size = os.path.getsize(file_path)
        print(f"File size: {file_size} bytes ({file_size / (1024*1024*1024):.2f} GB)")
        
        if file_size <= max_size:
            print("File is under size limit, no splitting needed")
            return [file_path]

        chunks = []
        chunk_num = 1
        
        p = Path(file_path)
        base_name = p.stem
        extension = p.suffix
        folder = p.parent

        print(f"Splitting into chunks of max {max_size} bytes each")
        
        try:
            with open(file_path, 'rb') as input_file:
                while True:
                    chunk_data = input_file.read(int(max_size))
                    if not chunk_data:
                        break
                    
                    output_file = folder / f"{base_name}.part{chunk_num:03d}{extension}"
                    
                    print(f"Creating chunk {chunk_num}: {output_file}")
                    
                    with open(output_file, 'wb') as output_chunk:
                        output_chunk.write(chunk_data)
                    
                    if os.path.exists(output_file):
                        chunk_size = os.path.getsize(output_file)
                        print(f"✅ Created chunk {chunk_num}: {chunk_size} bytes")
                        chunks.append(str(output_file))
                        chunk_num += 1
                    else:
                        print(f"❌ Failed to create chunk {chunk_num}")
                        break

        except Exception as split_error:
            print(f"Error during file splitting: {split_error}")
            # Clean up any partial chunks
            for chunk_path in chunks:
                try:
                    if os.path.exists(chunk_path):
                        os.remove(chunk_path)
                except Exception:
                    pass
            return [file_path]

        if chunks:
            print(f"✅ Successfully split file into {len(chunks)} parts")
            return chunks
        else:
            print("❌ No chunks created, returning original file")
            return [file_path]

    except Exception as e:
        print(f"❌ Error splitting file: {e}")
        import traceback
        traceback.print_exc()
        return [file_path]

# ==================== SIMPLIFIED PROGRESS UPDATE ====================

async def update_upload_progress_simple(status_msg, progress_data, file_name, part_num=None, total_parts=None):
    """Simplified upload progress update"""
    try:
        last_update = 0
        while progress_data['current'] < progress_data['total']:
            current = progress_data['current']
            total = progress_data['total']
            
            if current == 0:
                await asyncio.sleep(1)
                continue
            
            # Only update every 3 seconds to avoid rate limits
            now = time.time()
            if now - last_update < 3:
                await asyncio.sleep(1)
                continue
            
            last_update = now
            
            total_time = now - progress_data['start_time']
            avg_speed = current / total_time if total_time > 0 else 0
            
            remaining_bytes = total - current
            eta = remaining_bytes / avg_speed if avg_speed > 0 else 0
            
            percentage = (current / total) * 100 if total > 0 else 0
            progress_bar = create_progress_bar(percentage)
            
            if part_num and total_parts:
                status_text = f"<b>📤 sᴇɴᴅɪɴɢ ᴘᴀʀᴛ {part_num}/{total_parts}</b>\n\n"
            else:
                status_text = f"<b>📤 sᴇɴᴅɪɴɢ ᴛᴏ ʏᴏᴜ...</b>\n\n"
            
            status_text += (
                f"<b>📁 ғɪʟᴇ:</b> <code>{file_name[:40]}{'...' if len(file_name) > 40 else ''}</code>\n"
                f"<b>💾 sɪᴢᴇ:</b> {format_bytes(total)}\n\n"
                f"<b>📊 ᴘʀᴏɢʀᴇss:</b>\n"
                f"<code>{progress_bar}</code> <b>{percentage:.1f}%</b>\n\n"
                f"<b>📤 sᴇɴᴛ:</b> {format_bytes(current)} / {format_bytes(total)}\n"
                f"<b>📈 sᴘᴇᴇᴅ:</b> {format_bytes(avg_speed)}/s\n"
                f"<b>⏱️ ᴇᴛᴀ:</b> {format_time(eta)}"
            )
            
            try:
                await status_msg.edit_text(status_text, parse_mode=ParseMode.HTML)
            except Exception as edit_error:
                print(f"Error updating progress: {edit_error}")
                # Don't break the loop for edit errors
            
            await asyncio.sleep(2)
            
    except asyncio.CancelledError:
        print("Progress update task cancelled")
        pass
    except Exception as e:
        print(f"Progress update error: {e}")
        pass

# ==================== UTILITY FUNCTIONS ====================

def sanitize_filename(filename):
    """Sanitize filename for better compatibility"""
    import re
    
    try:
        # Remove or replace problematic characters
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        
        # Replace multiple spaces with single space
        filename = re.sub(r'\s+', ' ', filename)
        
        # Remove leading/trailing spaces and dots
        filename = filename.strip(' .')
        
        # Remove control characters
        filename = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', filename)
        
        # Limit filename length (keep extension)
        name, ext = os.path.splitext(filename)
        if len(name) > 200:  # Leave room for extension and path
            name = name[:200]
        
        # Ensure we don't have an empty filename
        if not name.strip():
            name = f"file_{int(time.time())}"
        
        sanitized = name + ext
        print(f"Sanitized filename: '{filename}' -> '{sanitized}'")
        return sanitized
        
    except Exception as e:
        print(f"Error sanitizing filename '{filename}': {e}")
        # Fallback to timestamp-based name
        timestamp = int(time.time())
        ext = os.path.splitext(filename)[1] if '.' in filename else ''
        return f"file_{timestamp}{ext}"

def is_video_file(file_path):
    """Check if file is a video based on extension"""
    try:
        video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv', '.m4v', '.3gp', '.ts', '.m2ts']
        file_ext = Path(file_path).suffix.lower()
        return file_ext in video_extensions
    except Exception as e:
        print(f"Error checking if file is video: {e}")
        return False

def create_progress_bar(percentage):
    """Create a progress bar string"""
    try:
        filled_length = int(percentage // 10)
        bar = '█' * filled_length + '░' * (10 - filled_length)
        return bar
    except Exception:
        return '░░░░░░░░░░'

def format_time(seconds):
    """Format time in seconds to readable format"""
    try:
        if seconds <= 0:
            return "ᴜɴᴋɴᴏᴡɴ"
        
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours}ʜ {minutes}ᴍ {secs}s"
        elif minutes > 0:
            return f"{minutes}ᴍ {secs}s"
        else:
            return f"{secs}s"
    except Exception:
        return "ᴜɴᴋɴᴏᴡɴ"

# ==================== PLACEHOLDER FUNCTIONS ====================

async def get_file_settings():
    """Get file upload settings - placeholder function"""
    try:
        # Return default settings if function not implemented
        return {
            'protect_content': False,
            'show_caption': True,
            'auto_delete': False,
            'auto_delete_time': 300,
            'inline_buttons': True,
            'spoiler_enabled': False
        }
    except Exception:
        return {
            'protect_content': False,
            'show_caption': True,
            'auto_delete': False,
            'auto_delete_time': 300,
            'inline_buttons': True,
            'spoiler_enabled': False
        }

async def is_premium_user(user_id):
    """Check if user is premium - placeholder function"""
    try:
        # Implement your premium user check logic here
        return False
    except Exception:
        return False

async def create_user_keyboard(is_premium):
    """Create user keyboard - placeholder function"""
    try:
        # Return None if not implemented
        return None
    except Exception:
        return None

async def generate_thumbnail(video_path, thumb_path, time_offset=10):
    """Generate thumbnail for video - placeholder function"""
    try:
        import subprocess
        
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-ss", str(time_offset),
            "-i", video_path,
            "-vframes", "1",
            "-vf", "scale=320:240",
            "-y", thumb_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        
        if result.returncode == 0 and os.path.exists(thumb_path):
            return True
        else:
            return False
            
    except Exception as e:
        print(f"Error generating thumbnail: {e}")
        return False

async def get_video_dimensions(video_path):
    """Get video dimensions - placeholder function"""
    try:
        import subprocess
        
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", "-select_streams", "v:0", video_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            if data.get('streams'):
                stream = data['streams'][0]
                width = stream.get('width', 1280)
                height = stream.get('height', 720)
                return width, height
        
        return 1280, 720
        
    except Exception as e:
        print(f"Error getting video dimensions: {e}")
        return 1280, 720

async def safe_edit_message(message, text, parse_mode):
    """Safely edit message with error handling"""
    try:
        await message.edit_text(text, parse_mode=parse_mode)
    except Exception as e:
        print(f"Error editing message: {e}")
        pass

def cleanup_files(directory):
    """Clean up files in directory"""
    try:
        import shutil
        if os.path.exists(directory):
            shutil.rmtree(directory)
            print(f"Cleaned up directory: {directory}")
    except Exception as e:
        print(f"Error cleaning up directory {directory}: {e}")

print("✅ Enhanced download module with proper error handling loaded successfully")

async def upload_single_file_to_user(client, message, file_path, progress_tracker, part_num=None, total_parts=None):
    """Upload single file to user with enhanced features"""
    try:
        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        status_msg = progress_tracker.status_msg
        
        # Get user settings
        settings = await get_file_settings()
        is_premium = await is_premium_user(message.from_user.id)
        
        protect_content = settings.get('protect_content', False)
        show_caption = settings.get('show_caption', True)
        auto_delete = settings.get('auto_delete', False)
        auto_delete_time = settings.get('auto_delete_time', 300)
        inline_buttons = settings.get('inline_buttons', True)
        spoiler_enabled = settings.get('spoiler_enabled', False)
        
        # Create caption
        if part_num and total_parts:
            caption = f"<b>{file_name}</b>\n<b>📦 Part {part_num}/{total_parts} | {format_bytes(file_size)}</b>" if show_caption else None
        else:
            caption = f"<b>{file_name}</b> | <b>{format_bytes(file_size)}</b>" if show_caption else None
        
        keyboard = await create_user_keyboard(is_premium) if inline_buttons else None
        
        # Progress tracking
        upload_start_time = time.time()
        progress_data = {
            'current': 0,
            'total': file_size,
            'start_time': upload_start_time
        }
        
        def upload_progress(current, total):
            progress_data['current'] = current
            progress_data['total'] = total
        
        # Start progress update task
        progress_task = asyncio.create_task(update_upload_progress(status_msg, progress_data, file_name, part_num, total_parts))
        
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
        
        user_message = None
        metadata = progress_tracker.metadata
        
        try:
            if file_path.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm')):
                # Send as video with spoiler support
                user_message = await client.send_video(
                    chat_id=message.chat.id,
                    video=file_path,
                    caption=caption,
                    supports_streaming=True,
                    thumb=thumbnail_path,
                    duration=int(metadata.get('duration', 0)) if metadata else 0,
                    width=width,
                    height=height,
                    progress=upload_progress,
                    parse_mode=ParseMode.HTML if caption else None,
                    reply_markup=keyboard,
                    protect_content=protect_content,
                    has_spoiler=spoiler_enabled  # Spoiler for videos
                )
            elif file_path.lower().endswith(('.mp3', '.m4a', '.wav', '.flac', '.ogg')):
                # Send as audio
                user_message = await client.send_audio(
                    chat_id=message.chat.id,
                    audio=file_path,
                    caption=caption,
                    duration=int(metadata.get('duration', 0)) if metadata else 0,
                    performer=metadata.get('uploader', 'Unknown') if metadata else 'Unknown',
                    title=metadata.get('title', file_name) if metadata else file_name,
                    thumb=thumbnail_path,
                    progress=upload_progress,
                    parse_mode=ParseMode.HTML if caption else None,
                    reply_markup=keyboard,
                    protect_content=protect_content
                )
            else:
                # Send as document
                user_message = await client.send_document(
                    chat_id=message.chat.id,
                    document=file_path,
                    caption=caption,
                    thumb=thumbnail_path,
                    progress=upload_progress,
                    parse_mode=ParseMode.HTML if caption else None,
                    reply_markup=keyboard,
                    protect_content=protect_content
                )
        
        except Exception as e:
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
        
        # Handle auto delete
        if auto_delete and user_message:
            warning_message = await message.reply_text(
                f"<b>⚠️ ᴄᴏᴘʏʀɪɢʜᴛ ᴡᴀʀɴɪɴɢ</b>\n\n"
                f"<b>📁 ғɪʟᴇ:</b> <code>{file_name}</code>\n"
                f"<blockquote><b>⏰ ᴛʜɪs ғɪʟᴇ ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ ɪɴ:</b> {format_time(auto_delete_time)}</blockquote>\n\n"
                f"<i>💡 ғᴏʀᴡᴀʀᴅ ɪᴛ ǫᴜɪᴄᴋʟʏ ʙᴇғᴏʀᴇ ɪᴛ's ʀᴇᴍᴏᴠᴇᴅ..!</i>",
                parse_mode=ParseMode.HTML
            )
            
            asyncio.create_task(auto_delete_message_with_notification(
                client,
                message.chat.id,
                user_message.id,
                warning_message.id,
                file_name,
                auto_delete_time
            ))
        
        return user_message
        
    except Exception as e:
        await status_msg.edit_text(
            f"<b>❌ ᴜᴘʟᴏᴀᴅ ғᴀɪʟᴇᴅ!</b>\n\n"
            f"<b>📁 ғɪʟᴇ:</b> <code>{file_name}</code>\n"
            f"<b>❌ ᴇʀʀᴏʀ:</b> <code>{str(e)}</code>",
            parse_mode=ParseMode.HTML
        )
        return None

# ==================== COPY TO DUMPS ====================
async def copy_to_dumps(client, user_message, file_name, file_size, user_info):
    """Copy user message to all dump channels"""
    try:
        # Create dump caption without inline keyboard
        dump_caption = f"<b>{file_name}</b> | <b>{format_bytes(file_size)}</b>\n<b>ʟᴇᴇᴄʜᴇᴅ ʙʏ :</b> <a href='tg://user?id={user_info['id']}'>{user_info['name']}</a>"
        
        for dump_id in DUMP_CHAT_IDS:
            try:
                if user_message.video:
                    await client.send_video(
                        chat_id=dump_id,
                        video=user_message.video.file_id,
                        caption=dump_caption,
                        supports_streaming=True,
                        thumb=user_message.video.thumbs[0].file_id if user_message.video.thumbs else None,
                        duration=user_message.video.duration,
                        width=user_message.video.width,
                        height=user_message.video.height,
                        parse_mode=ParseMode.HTML,
                        has_spoiler=False  # No spoiler in dump channels
                    )
                elif user_message.audio:
                    await client.send_audio(
                        chat_id=dump_id,
                        audio=user_message.audio.file_id,
                        caption=dump_caption,
                        duration=user_message.audio.duration,
                        performer=user_message.audio.performer,
                        title=user_message.audio.title,
                        thumb=user_message.audio.thumbs[0].file_id if user_message.audio.thumbs else None,
                        parse_mode=ParseMode.HTML
                    )
                elif user_message.document:
                    await client.send_document(
                        chat_id=dump_id,
                        document=user_message.document.file_id,
                        caption=dump_caption,
                        thumb=user_message.document.thumbs[0].file_id if user_message.document.thumbs else None,
                        parse_mode=ParseMode.HTML
                    )
                elif user_message.photo:
                    await client.send_photo(
                        chat_id=dump_id,
                        photo=user_message.photo.file_id,
                        caption=dump_caption,
                        parse_mode=ParseMode.HTML
                    )
                elif user_message.animation:
                    await client.send_animation(
                        chat_id=dump_id,
                        animation=user_message.animation.file_id,
                        caption=dump_caption,
                        duration=user_message.animation.duration,
                        width=user_message.animation.width,
                        height=user_message.animation.height,
                        thumb=user_message.animation.thumbs[0].file_id if user_message.animation.thumbs else None,
                        parse_mode=ParseMode.HTML
                    )
                else:
                    # Fallback to copy_message
                    await client.copy_message(
                        chat_id=dump_id,
                        from_chat_id=user_message.chat.id,
                        message_id=user_message.id,
                        caption=dump_caption,
                        parse_mode=ParseMode.HTML
                    )
                
            except Exception as e:
                pass  # Continue with other dump channels if one fails
                
    except Exception as e:
        pass

# ==================== PROGRESS UPDATE FUNCTIONS ====================

async def update_progress_concurrent(progress_tracker):
    """Update progress message for concurrent downloads"""
    try:
        status_msg = progress_tracker.status_msg
        
        while progress_tracker.status != "ᴄᴏᴍᴘʟᴇᴛᴇᴅ":
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
                progress_text = f"<b>›› {progress_tracker.status}</b>"
            
            await safe_edit_message(status_msg, progress_text, ParseMode.HTML)
            await asyncio.sleep(3)
            
    except asyncio.CancelledError:
        pass
    except Exception as e:
        pass

async def update_upload_progress(status_msg, progress_data, file_name, part_num=None, total_parts=None):
    """Update upload progress for user uploads"""
    try:
        while progress_data['current'] < progress_data['total']:
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
                status_text = f"<b>📤 sᴇɴᴅɪɴɢ ᴘᴀʀᴛ {part_num}/{total_parts}</b>\n\n"
            else:
                status_text = f"<b>📤 sᴇɴᴅɪɴɢ ᴛᴏ ʏᴏᴜ...</b>\n\n"
            
            status_text += (
                f"<b>📁 ғɪʟᴇ:</b> <code>{file_name}</code>\n"
                f"<b>💾 sɪᴢᴇ:</b> {format_bytes(total)}\n\n"
                f"<b>📊 ᴘʀᴏɢʀᴇss:</b>\n"
                f"<code>{progress_bar}</code> <b>{percentage:.1f}%</b>\n\n"
                f"<b>📤 sᴇɴᴛ:</b> {format_bytes(current)} / {format_bytes(total)}\n"
                f"<b>📈 sᴘᴇᴇᴅ:</b> {format_bytes(avg_speed)}/s\n"
                f"<b>⏱️ ᴇᴛᴀ:</b> {format_time(eta)}"
            )
            
            await safe_edit_message(status_msg, status_text, ParseMode.HTML)
            await asyncio.sleep(2)
            
    except asyncio.CancelledError:
        pass
    except Exception as e:
        pass

# ==================== AUTO DELETE FUNCTION ====================

async def auto_delete_message_with_notification(client, chat_id, file_message_id, warning_message_id, file_name, delay_seconds):
    """Auto delete message after specified time with notification update"""
    try:
        await asyncio.sleep(delay_seconds)
        
        try:
            await client.delete_messages(chat_id, file_message_id)
            
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
                except Exception:
                    pass
                    
        except Exception:
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
                except Exception:
                    pass
                    
    except Exception:
        pass

# ==================== UTILITY FUNCTIONS ====================

def is_video_file(file_path):
    """Check if file is a video"""
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type and mime_type.startswith("video/")

def download_video(url, ydl_opts):
    """Download video using yt-dlp with optimizations"""
    try:
        import yt_dlp
        from urllib.parse import urlparse
        
        domain = urlparse(url).netloc.lower()
        
        # Optimized options
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
                'format': 'best[height<=2160]/best[height<=1080]/best[height<=720]/best',  # Support up to 2K
                'concurrent_fragment_downloads': 2,
                'cookiefile': None,  # We'll use cookies string instead
                'http_headers': {
                    **speed_opts.get('http_headers', {}),
                    'Cookie': 'ig_did=5F30EC1A-E526-4D97-B373-19788410E2CE; csrftoken=ycZ7eUDnykKtR8upEyrek5; datr=66fOZ5Qiu1l_cU4uP2cKjA69; mid=Z_zyYwALAAG7Oecyackg3FnHYIbK; ds_user_id=53761245194; ps_l=1; ps_n=1; sessionid=53761245194%3Aiuj8gwGXuvt5z5%3A26%3AAYdoBvwXYdn8FhG6dPUPV2TNN5oHTYLIjDfFerlypw; dpr=1.25; wd=775x735; rur="HIL\05453761245194\0541781864652:01fef3e329bbcd4bb1db01afb346ef2a68726a2965cab4061f3f388195412625b8f76154"',
                    'Origin': 'https://www.instagram.com',
                    'Referer': 'https://www.instagram.com/',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': 'ycZ7eUDnykKtR8upEyrek5',
                    'X-Instagram-AJAX': '1',
                },
                'extractor_args': {
                    'instagram': {
                        'api_version': 'v1',
                        'include_stories': True,
                    }
                }
            })

        elif any(adult_site in domain for adult_site in ['pornhub', 'xvideos', 'xnxx', 'xhamster']):
            speed_opts.update({
                'format': 'best[height<=1080][protocol^=https]/best[height<=720][protocol^=https]/best',
                'concurrent_fragment_downloads': 8,  # Increased from 6
                'http_chunk_size': 2 * 1024 * 1024,  # 2MB chunks for better throughput
                'socket_timeout': 45,  # Increased timeout
                'retries': 8,  # More retries for stability
                'fragment_retries': 8,
                'http_headers': {
                    **speed_opts['http_headers'],
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'video/webm,video/ogg,video/*;q=0.9,application/ogg;q=0.7,audio/*;q=0.6,*/*;q=0.5',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'video',
                    'Sec-Fetch-Mode': 'no-cors',
                    'Sec-Fetch-Site': 'same-origin',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache',
                    'Referer': f'https://{domain}/',
                    'Origin': f'https://{domain}',
                },
                'extractor_args': {
                    'generic': {
                        'variant_m3u8': True,
                    }
                },
                'hls_prefer_native': True,  # Use native HLS downloader for better speed
                'external_downloader': None,  # Let yt-dlp handle it natively
                'prefer_insecure': False,  # Use HTTPS for better reliability
                'no_check_certificate': False,  # Enable certificate checking for these sites
            })

        else:
            speed_opts.update({
                'format': 'best[height<=720]/best[height<=480]/best',  # Also improved this
                'concurrent_fragment_downloads': 3,
            })
        
        try:
            with yt_dlp.YoutubeDL(speed_opts) as ydl:
                ydl.download([url])
                return True
                
        except Exception:
            # Fallback with conservative settings
            conservative_opts = {
                **ydl_opts,
                'format': 'best/worst',  # Changed to prioritize best quality in fallback
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
                    return True
            except Exception:
                return False
                        
    except Exception:
        return False

# ==================== CANCEL COMMAND ====================

@Client.on_message(filters.private & filters.command("cancel"))
async def cancel_downloads(client: Client, message: Message):
    """Cancel all active downloads for user"""
    try:
        user_id = message.from_user.id
        
        if user_id not in active_downloads or not active_downloads[user_id]:
            await message.reply_text(
                "<b>❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅs</b>\n\n"
                "ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴀɴʏ ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅs ᴛᴏ ᴄᴀɴᴄᴇʟ.",
                parse_mode=ParseMode.HTML
            )
            return
        
        cancelled_count = len(active_downloads[user_id])
        
        # Update all status messages
        for tracker in active_downloads[user_id]:
            try:
                if tracker.status_msg:
                    await tracker.status_msg.edit_text(
                        "<b>❌ ᴅᴏᴡɴʟᴏᴀᴅ ᴄᴀɴᴄᴇʟʟᴇᴅ</b>\n\n"
                        "ᴅᴏᴡɴʟᴏᴀᴅ ᴡᴀs ᴄᴀɴᴄᴇʟʟᴇᴅ ʙʏ ᴜsᴇʀ.",
                        parse_mode=ParseMode.HTML
                    )
            except Exception:
                pass
        
        # Clear active downloads
        del active_downloads[user_id]
        
        await message.reply_text(
            f"<b>✅ ᴅᴏᴡɴʟᴏᴀᴅs ᴄᴀɴᴄᴇʟʟᴇᴅ</b>\n\n"
            f"<b>🚫 ᴄᴀɴᴄᴇʟʟᴇᴅ:</b> {cancelled_count} ᴅᴏᴡɴʟᴏᴀᴅ(s)\n"
            f"<b>✨ sᴛᴀᴛᴜs:</b> ᴀʟʟ ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅs sᴛᴏᴘᴘᴇᴅ",
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        await message.reply_text(
            f"<b>❌ ᴇʀʀᴏʀ ᴄᴀɴᴄᴇʟʟɪɴɢ</b>\n\n<code>{str(e)}</code>",
            parse_mode=ParseMode.HTML
        )

# ==================== STATUS COMMAND ====================

@Client.on_message(filters.private & filters.command("status"))
async def download_status(client: Client, message: Message):
    """Show current download status for user"""
    try:
        user_id = message.from_user.id
        
        if user_id not in active_downloads or not active_downloads[user_id]:
            await message.reply_text(
                "<b>📊 ᴅᴏᴡɴʟᴏᴀᴅ sᴛᴀᴛᴜs</b>\n\n"
                "<b>✅ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅs</b>\n\n"
                f"<b>📈 ᴍᴀx ᴄᴏɴᴄᴜʀʀᴇɴᴛ:</b> {MAX_CONCURRENT_DOWNLOADS}\n"
                "<i>sᴇɴᴅ ᴀ ʟɪɴᴋ ᴛᴏ sᴛᴀʀᴛ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ</i>",
                parse_mode=ParseMode.HTML
            )
            return
        
        status_text = f"<b>📊 ᴅᴏᴡɴʟᴏᴀᴅ sᴛᴀᴛᴜs</b>\n\n"
        status_text += f"<b>🔄 ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅs:</b> {len(active_downloads[user_id])}/{MAX_CONCURRENT_DOWNLOADS}\n\n"
        
        for i, tracker in enumerate(active_downloads[user_id], 1):
            file_name = os.path.basename(tracker.filename) if tracker.filename else "Unknown"
            if len(file_name) > 30:
                file_name = file_name[:27] + "..."
            
            if tracker.total_size > 0:
                percentage = (tracker.downloaded / tracker.total_size) * 100
                downloaded_str = format_bytes(tracker.downloaded)
                total_str = format_bytes(tracker.total_size)
                speed_str = format_bytes(tracker.speed) + "/s" if tracker.speed > 0 else "0 B/s"
                
                status_text += f"<b>📥 ᴅᴏᴡɴʟᴏᴀᴅ #{i}</b>\n"
                status_text += f"<b>📁 ғɪʟᴇ:</b> <code>{file_name}</code>\n"
                status_text += f"<b>📊 ᴘʀᴏɢʀᴇss:</b> {percentage:.1f}%\n"
                status_text += f"<b>📦 sɪᴢᴇ:</b> {downloaded_str}/{total_str}\n"
                status_text += f"<b>⚡ sᴘᴇᴇᴅ:</b> {speed_str}\n"
                status_text += f"<b>⏱️ sᴛᴀᴛᴜs:</b> {tracker.status}\n\n"
            else:
                status_text += f"<b>📥 ᴅᴏᴡɴʟᴏᴀᴅ #{i}</b>\n"
                status_text += f"<b>📁 ғɪʟᴇ:</b> <code>{file_name}</code>\n"
                status_text += f"<b>⏱️ sᴛᴀᴛᴜs:</b> {tracker.status}\n\n"
        
        status_text += f"<i>💡 ᴜsᴇ /cancel ᴛᴏ sᴛᴏᴘ ᴀʟʟ ᴅᴏᴡɴʟᴏᴀᴅs</i>"
        
        await message.reply_text(status_text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        await message.reply_text(
            f"<b>❌ ᴇʀʀᴏʀ ɢᴇᴛᴛɪɴɢ sᴛᴀᴛᴜs</b>\n\n<code>{str(e)}</code>",
            parse_mode=ParseMode.HTML
        )

# ==================== CLEANUP ON STARTUP ====================

async def cleanup_on_startup():
    """Clean up any leftover download directories on startup"""
    try:
        downloads_dir = "./downloads/"
        if os.path.exists(downloads_dir):
            for item in os.listdir(downloads_dir):
                item_path = os.path.join(downloads_dir, item)
                if os.path.isdir(item_path):
                    try:
                        cleanup_files(item_path)
                    except Exception:
                        pass
    except Exception:
        pass

# Initialize cleanup on module load
asyncio.create_task(cleanup_on_startup())

print("✅ Enhanced download module loaded successfully with concurrent support")
