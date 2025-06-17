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

user_client = None

def split_file(file_path, chunk_size=1.98 * 1024 * 1024 * 1024):  # 1.98GB
    """Split large files into smaller chunks"""
    try:
        file_size = os.path.getsize(file_path)
        if file_size <= chunk_size:
            return [file_path]  # No need to split
        
        file_name = os.path.basename(file_path)
        file_dir = os.path.dirname(file_path)
        name, ext = os.path.splitext(file_name)
        
        chunks = []
        chunk_num = 1
        
        with open(file_path, 'rb') as input_file:
            while True:
                chunk_data = input_file.read(int(chunk_size))
                if not chunk_data:
                    break
                
                chunk_filename = f"{name}.part{chunk_num:03d}{ext}"
                chunk_path = os.path.join(file_dir, chunk_filename)
                
                with open(chunk_path, 'wb') as chunk_file:
                    chunk_file.write(chunk_data)
                
                chunks.append(chunk_path)
                chunk_num += 1
        
        # Remove original file after splitting
        os.remove(file_path)
        print(f"✅ File split into {len(chunks)} parts")
        return chunks
        
    except Exception as e:
        print(f"❌ Error splitting file: {e}")
        return [file_path]
    
async def register_new_user(user_id, username, first_name):
    """Register new user in database - simplified version to avoid conflicts"""
    try:
        # Just ensure user exists in database
        user = await get_user(user_id)
        
        # Only update last_activity - don't touch username/first_name to avoid conflicts
        await user_data.update_one(
            {'_id': user_id},
            {'$set': {'last_activity': datetime.now()}},
            upsert=True
        )
        
        print(f"✅ User {user_id} activity updated")
        return user
        
    except Exception as e:
        print(f"❌ Error updating user activity {user_id}: {e}")
        # Just return the user data without updating
        return await get_user(user_id)

# Get dump channels from config (fixed)
DUMP_CHAT_IDS = Config.DUMP_CHAT_IDS

# Global variables to track downloads - UPDATED FOR MULTIPLE DOWNLOADS
active_downloads = defaultdict(list)  # Changed to list to store multiple downloads per user
download_counter = 0  # Global counter for unique download IDs

class ProgressTracker:
    def __init__(self, download_id, url):
        self.download_id = download_id
        self.url = url
        self.downloaded = 0
        self.total_size = 0
        self.speed = 0
        self.eta = 0
        self.filename = "Unknown"
        self.status = "ɪɴɪᴛɪᴀʟɪᴢɪɴɢ"
        self.start_time = time.time()
        self.last_update = 0
        self.upload_progress = 0
        self.upload_total = 0

def get_active_download_count(user_id):
    """Get number of active downloads for a user"""
    return len(active_downloads.get(user_id, []))

def add_active_download(user_id, download_id, url):
    """Add a new active download for user"""
    global download_counter
    download_counter += 1
    
    tracker = ProgressTracker(download_id, url)
    active_downloads[user_id].append(tracker)
    
    print(f"📥 Added download {download_id} for user {user_id} (Total: {len(active_downloads[user_id])})")
    return tracker

def remove_active_download(user_id, download_id):
    """Remove completed download from active list"""
    if user_id in active_downloads:
        active_downloads[user_id] = [
            tracker for tracker in active_downloads[user_id] 
            if tracker.download_id != download_id
        ]
        
        # Clean up empty lists
        if not active_downloads[user_id]:
            del active_downloads[user_id]
        
        print(f"✅ Removed download {download_id} for user {user_id}")

def get_download_tracker(user_id, download_id):
    """Get specific download tracker"""
    if user_id in active_downloads:
        for tracker in active_downloads[user_id]:
            if tracker.download_id == download_id:
                return tracker
    return None

def format_bytes(bytes_value):
    """Format bytes to human readable format"""
    if bytes_value == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = int(math.floor(math.log(bytes_value, 1024)))
    p = math.pow(1024, i)
    s = round(bytes_value / p, 2)
    return f"{s} {size_names[i]}"

def format_time(seconds):
    """Format seconds to human readable time"""
    if seconds <= 0:
        return "Unknown"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"

def cleanup_files(directory):
    """Clean up downloaded files"""
    try:
        if os.path.exists(directory):
            for file in os.listdir(directory):
                file_path = os.path.join(directory, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    print(f"🗑️ Cleaned up: {file}")
            os.rmdir(directory)
            print(f"🗑️ Cleaned up directory: {directory}")
    except Exception as e:
        print(f"❌ Cleanup error: {e}")

async def update_progress(status_msg, user_id, download_id):
    """Update progress message for specific download"""
    try:
        last_edit_time = 0
        
        while True:
            current_time = time.time()
            
            # Update every 3 seconds to avoid flood limits
            if current_time - last_edit_time < 3:
                await asyncio.sleep(1)
                continue
            
            tracker = get_download_tracker(user_id, download_id)
            if not tracker:
                break
            
            if tracker.status == "ᴄᴏᴍᴘʟᴇᴛᴇᴅ":
                break
            
            try:
                # Calculate progress
                if tracker.total_size > 0:
                    progress_percent = (tracker.downloaded / tracker.total_size) * 100
                    progress_bar = create_progress_bar(progress_percent)
                else:
                    progress_percent = 0
                    progress_bar = "▱▱▱▱▱▱▱▱▱▱"
                
                # Format speed and ETA
                speed_text = format_bytes(tracker.speed) + "/s" if tracker.speed > 0 else "0 B/s"
                eta_text = format_time(tracker.eta) if tracker.eta > 0 else "Unknown"
                
                # Get file name (truncate if too long)
                filename = tracker.filename
                if len(filename) > 30:
                    filename = filename[:27] + "..."
                
                # Count active downloads for this user
                active_count = get_active_download_count(user_id)
                
                progress_text = (
                    f"<b>📥 ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ... ({active_count} ᴀᴄᴛɪᴠᴇ)</b>\n\n"
                    f"<b>📁 ғɪʟᴇ:</b> <code>{filename}</code>\n"
                    f"<b>📊 ᴘʀᴏɢʀᴇss:</b> {progress_percent:.1f}%\n"
                    f"{progress_bar}\n"
                    f"<b>💾 sɪᴢᴇ:</b> {format_bytes(tracker.downloaded)} / {format_bytes(tracker.total_size)}\n"
                    f"<b>⚡ sᴘᴇᴇᴅ:</b> {speed_text}\n"
                    f"<b>⏱️ ᴇᴛᴀ:</b> {eta_text}\n"
                    f"<b>🆔 ᴅᴏᴡɴʟᴏᴀᴅ:</b> #{download_id}"
                )
                
                await status_msg.edit_text(progress_text, parse_mode=ParseMode.HTML)
                last_edit_time = current_time
                
            except Exception as e:
                if "message is not modified" not in str(e).lower():
                    print(f"❌ Progress update error: {e}")
            
            await asyncio.sleep(2)
            
    except asyncio.CancelledError:
        print(f"📊 Progress tracking cancelled for download {download_id}")
    except Exception as e:
        print(f"❌ Progress tracking error: {e}")

def create_progress_bar(percentage, length=10):
    """Create a visual progress bar"""
    filled = int(length * percentage / 100)
    bar = "▰" * filled + "▱" * (length - filled)
    return bar

async def upload_to_dump(client, file_path, dump_chat_id, progress_tracker, status_msg):
    """Upload file to dump channel with progress tracking"""
    try:
        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        
        print(f"📤 Uploading to dump {dump_chat_id}: {file_name}")
        
        # Upload progress callback
        async def upload_progress(current, total):
            try:
                progress_tracker.upload_progress = current
                progress_tracker.upload_total = total
                
                # Update status message every 3 seconds
                current_time = time.time()
                if hasattr(upload_progress, 'last_update'):
                    if current_time - upload_progress.last_update < 3:
                        return
                upload_progress.last_update = current_time
                
                percent = (current / total) * 100 if total > 0 else 0
                progress_bar = create_progress_bar(percent)
                
                upload_text = (
                    f"<b>📤 ᴜᴘʟᴏᴀᴅɪɴɢ...</b>\n\n"
                    f"<b>📁 ғɪʟᴇ:</b> <code>{file_name}</code>\n"
                    f"<b>📊 ᴘʀᴏɢʀᴇss:</b> {percent:.1f}%\n"
                    f"{progress_bar}\n"
                    f"<b>💾 sɪᴢᴇ:</b> {format_bytes(current)} / {format_bytes(total)}\n"
                    f"<b>🆔 ᴅᴏᴡɴʟᴏᴀᴅ:</b> #{progress_tracker.download_id}"
                )
                
                try:
                    await status_msg.edit_text(upload_text, parse_mode=ParseMode.HTML)
                except Exception:
                    pass  # Ignore edit errors during upload
                    
            except Exception as e:
                print(f"Upload progress error: {e}")
        
        # Determine file type and upload accordingly
        file_ext = os.path.splitext(file_name)[1].lower()
        
        if file_ext in ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv']:
            # Upload as video
            message = await client.send_video(
                chat_id=dump_chat_id,
                video=file_path,
                caption=f"📹 {file_name}\n💾 {format_bytes(file_size)}",
                progress=upload_progress,
                supports_streaming=True
            )
        elif file_ext in ['.mp3', '.m4a', '.wav', '.flac', '.ogg', '.aac']:
            # Upload as audio
            message = await client.send_audio(
                chat_id=dump_chat_id,
                audio=file_path,
                caption=f"🎵 {file_name}\n💾 {format_bytes(file_size)}",
                progress=upload_progress
            )
        else:
            # Upload as document
            message = await client.send_document(
                chat_id=dump_chat_id,
                document=file_path,
                caption=f"📄 {file_name}\n💾 {format_bytes(file_size)}",
                progress=upload_progress
            )
        
        print(f"✅ Upload successful to dump {dump_chat_id}")
        return message
        
    except Exception as e:
        print(f"❌ Upload failed to dump {dump_chat_id}: {e}")
        return None

def download_video(url, ydl_opts):
    """Download video using yt-dlp with enhanced error handling"""
    try:
        import yt_dlp
        from urllib.parse import urlparse
        
        domain = urlparse(url).netloc.lower()
        
        # Enhanced connection options
        connection_opts = {
            **ydl_opts,
            
            # Connection resilience
            'retries': 10,
            'fragment_retries': 10,
            'retry_sleep_functions': {
                'http': lambda n: min(4 ** n, 30),
                'fragment': lambda n: min(2 ** n, 10)
            },
            
            # Timeout settings
            'socket_timeout': 60,
            
            # Headers to avoid detection
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            },
            
            # SSL/TLS settings
            'no_check_certificate': True,
            'prefer_insecure': False,
            
            # Download optimization
            'concurrent_fragment_downloads': 1,
            'http_chunk_size': 512 * 1024,  # 512KB chunks
        }
        
        # Site-specific adjustments
        if any(adult_site in domain for adult_site in ['pornhub', 'xvideos', 'xnxx', 'xhamster']):
            print(f"🔞 Adult site detected: {domain}")
            connection_opts.update({
                'http_headers': {
                    **connection_opts['http_headers'],
                    'Referer': f'https://{domain}/',
                    'Origin': f'https://{domain}',
                },
                'socket_timeout': 120,
                'retries': 15,
                'age_limit': 18,
            })
            
        elif 'youtube' in domain:
            connection_opts.update({
                'format': 'best[height<=720]/best[height<=480]/worst',
                'extractor_args': {
                    'youtube': {
                        'skip': ['dash'],
                        'player_skip': ['js'],
                    }
                }
            })
            
        elif 'instagram' in domain:
            connection_opts.update({
                'http_headers': {
                    **connection_opts['http_headers'],
                    'X-Instagram-AJAX': '1',
                    'X-Requested-With': 'XMLHttpRequest',
                }
            })
        
        print(f"🔄 Attempting download from {domain}...")
        
        try:
            with yt_dlp.YoutubeDL(connection_opts) as ydl:
                ydl.download([url])
                print(f"✅ Download successful")
                return True
                
        except Exception as e:
            print(f"❌ Download failed: {e}")
            return False
                        
    except Exception as e:
        print(f"❌ Critical download error: {e}")
        return False

async def download_and_send(client, message, status_msg, url, user_id, download_id):
    """Download video and send to user with progress tracking - UPDATED FOR MULTIPLE DOWNLOADS"""
    try:
        # Create download directory
        download_dir = f"./downloads/{user_id}_{download_id}/"
        os.makedirs(download_dir, exist_ok=True)
        
        progress_tracker = get_download_tracker(user_id, download_id)
        if not progress_tracker:
            await status_msg.edit_text("❌ <b>ᴅᴏᴡɴʟᴏᴀᴅ ᴛʀᴀᴄᴋᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ!</b>", parse_mode=ParseMode.HTML)
            return
        
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
        ydl_opts = {
            'outtmpl': f'{download_dir}%(title)s.%(ext)s',
            'format': 'best[filesize<2G]/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'progress_hooks': [progress_hook],
        }
        
        # Start progress update task for downloading
        progress_task = asyncio.create_task(update_progress(status_msg, user_id, download_id))
        
        # Download in a separate thread
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(None, download_video, url, ydl_opts)
        
        # Cancel progress updates
        progress_task.cancel()
        
        if not success:
            await status_msg.edit_text(
                f"<b>❌ ᴅᴏᴡɴʟᴏᴀᴅ ғᴀɪʟᴇᴅ!</b>\n\n"
                f"<b>🆔 ᴅᴏᴡɴʟᴏᴀᴅ:</b> #{download_id}\n"
                "ᴛʜᴇ ᴠɪᴅᴇᴏ ᴄᴏᴜʟᴅ ɴᴏᴛ ʙᴇ ᴅᴏᴡɴʟᴏᴀᴅᴇᴅ.",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Show download complete message
        await status_msg.edit_text(
            f"<b>✅ ᴅᴏᴡɴʟᴏᴀᴅ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!</b>\n\n"
            f"<b>🆔 ᴅᴏᴡɴʟᴏᴀᴅ:</b> #{download_id}\n"
            f"<b>📋 ᴘʀᴇᴘᴀʀɪɴɢ ғɪʟᴇs ғᴏʀ ᴜᴘʟᴏᴀᴅ...</b>",
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
                f"<b>❌ ɴᴏ ғɪʟᴇs ғᴏᴜɴᴅ!</b>\n\n"
                f"<b>🆔 ᴅᴏᴡɴʟᴏᴀᴅ:</b> #{download_id}",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Process each downloaded file
        uploaded_successfully = False
        
        for file_path in downloaded_files:
            try:
                file_size = os.path.getsize(file_path)
                file_name = os.path.basename(file_path)
                
                # Check file size and split if necessary
                if file_size > 2 * 1024 * 1024 * 1024:  # 2GB
                    print(f"📦 File too large, splitting: {file_name}")
                    file_chunks = split_file(file_path)
                else:
                    file_chunks = [file_path]
                
                # Process each chunk
                for chunk_path in file_chunks:
                    chunk_size = os.path.getsize(chunk_path)
                    chunk_name = os.path.basename(chunk_path)
                    
                    print(f"📤 Starting upload: {chunk_name} ({format_bytes(chunk_size)})")
                    
                    # Upload to first dump channel
                    dump_message = await upload_to_dump(client, chunk_path, DUMP_CHAT_IDS[0], progress_tracker, status_msg)
                    
                    if dump_message:
                        # Show upload complete message briefly
                        await status_msg.edit_text(
                            f"<b>✅ ᴜᴘʟᴏᴀᴅ sᴜᴄᴄᴇssғᴜʟ!</b>\n\n"
                            f"<b>📁 ғɪʟᴇ:</b> <code>{chunk_name}</code>\n"
                            f"<b>💾 sɪᴢᴇ:</b> {format_bytes(chunk_size)}\n"
                            f"<b>🆔 ᴅᴏᴡɴʟᴏᴀᴅ:</b> #{download_id}\n"
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
                        
                        # Update status for sending to user
                        await status_msg.edit_text(
                            f"<b>📤 sᴇɴᴅɪɴɢ ᴛᴏ ʏᴏᴜ...</b>\n\n"
                            f"<b>📁 ғɪʟᴇ:</b> <code>{chunk_name}</code>\n"
                            f"<b>🆔 ᴅᴏᴡɴʟᴏᴀᴅ:</b> #{download_id}",
                            parse_mode=ParseMode.HTML
                        )
                        
                        # Create inline keyboard for user messages
                        from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                        user_keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton("📺 ᴍᴏʀᴇ ᴠɪᴅᴇᴏs", url="https://t.me/shizukawachan/20")]
                        ])
                        
                        # Send to user WITH inline keyboard
                        try:
                            user_message = await client.copy_message(
                                chat_id=message.chat.id,
                                from_chat_id=DUMP_CHAT_IDS[0],
                                message_id=dump_message.id,
                                reply_markup=user_keyboard
                            )
                        except Exception as e:
                            print(f"❌ Error sending to user: {e}")
                            # Fallback: send without keyboard
                            await client.copy_message(
                                chat_id=message.chat.id,
                                from_chat_id=DUMP_CHAT_IDS[0],
                                message_id=dump_message.id
                            )
                        
                        uploaded_successfully = True
                        
                    else:
                        await message.reply_text(
                            f"<b>❌ ғᴀɪʟᴇᴅ ᴛᴏ ᴜᴘʟᴏᴀᴅ:</b> {chunk_name}\n"
                            f"<b>🆔 ᴅᴏᴡɴʟᴏᴀᴅ:</b> #{download_id}",
                            parse_mode=ParseMode.HTML
                        )
                
                # Update database stats
                if uploaded_successfully:
                    file_ext = os.path.splitext(file_name)[1].lower()
                    if file_ext in ['.mp4', '.mkv', '.avi', '.mov', '.webm']:
                        file_type = 'video'
                    elif file_ext in ['.mp3', '.m4a', '.wav', '.flac', '.ogg']:
                        file_type = 'audio'
                    else:
                        file_type = 'document'
                    
                    username = message.from_user.first_name or message.from_user.username or "Unknown"
                    await update_download_stats(user_id, username, url, file_size, file_type)
                
            except Exception as e:
                print(f"❌ Error processing file {file_path}: {e}")
                await message.reply_text(
                    f"<b>❌ ғᴀɪʟᴇᴅ ᴛᴏ sᴇɴᴅ:</b> {os.path.basename(file_path)}\n"
                    f"<b>🆔 ᴅᴏᴡɴʟᴏᴀᴅ:</b> #{download_id}",
                    parse_mode=ParseMode.HTML
                )
        
        # Delete the status message after everything is done
        if uploaded_successfully:
            try:
                await asyncio.sleep(2)
                await status_msg.delete()
            except Exception:
                await status_msg.edit_text(
                    f"<b>✅ ᴅᴏᴡɴʟᴏᴀᴅ #{download_id} ᴄᴏᴍᴘʟᴇᴛᴇᴅ!</b>",
                    parse_mode=ParseMode.HTML
                )
        else:
            await status_msg.edit_text(
                f"<b>❌ ᴅᴏᴡɴʟᴏᴀᴅ #{download_id} ғᴀɪʟᴇᴅ!</b>\n\n"
                "ɴᴏ ғɪʟᴇs ᴜᴘʟᴏᴀᴅᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!",
                parse_mode=ParseMode.HTML
            )
        
    except Exception as e:
        print(f"❌ Error in download_and_send: {e}")
        await status_msg.edit_text(
            f"<b>❌ ᴇʀʀᴏʀ:</b> {str(e)}\n"
            f"<b>🆔 ᴅᴏᴡɴʟᴏᴀᴅ:</b> #{download_id}",
            parse_mode=ParseMode.HTML
        )
    
    finally:
        # Cleanup
        cleanup_files(f"./downloads/{user_id}_{download_id}/")
        remove_active_download(user_id, download_id)

@Client.on_message(filters.text & filters.private & ~filters.command([
    "start", "help", "stats", "mystats", "history", "leaderboard", "ping", "speedtest",
    "downloads", "cancel", "clearall", "globalstats", "clearuser", "addchannel", 
    "removechannel", "showchannels", "cleanup"
]))
async def handle_url(client: Client, message: Message):
    """Handle URL messages with multiple download support"""
    try:
        # Check subscription first
        if not await check_subscription(client, message):
            return
        
        user_id = message.from_user.id
        username = message.from_user.first_name or message.from_user.username or "Unknown"
        url = message.text.strip()
        
        # Register/update user
        await register_new_user(user_id, username, message.from_user.first_name or "")
        
        # Basic URL validation
        if not (url.startswith('http://') or url.startswith('https://')):
            await message.reply_text(
                "<b>❌ ɪɴᴠᴀʟɪᴅ ᴜʀʟ!</b>\n\n"
                "ᴘʟᴇᴀsᴇ sᴇɴᴅ ᴀ ᴠᴀʟɪᴅ ᴜʀʟ sᴛᴀʀᴛɪɴɢ ᴡɪᴛʜ http:// ᴏʀ https://",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Check current active downloads for user
        current_downloads = get_active_download_count(user_id)
        max_concurrent = 3  # Allow up to 3 concurrent downloads per user
        
        if current_downloads >= max_concurrent:
            await message.reply_text(
                f"<b>⚠️ ᴍᴀx ᴅᴏᴡɴʟᴏᴀᴅs ʀᴇᴀᴄʜᴇᴅ!</b>\n\n"
                f"ʏᴏᴜ ᴄᴜʀʀᴇɴᴛʟʏ ʜᴀᴠᴇ <b>{current_downloads}</b> ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅs.\n"
                f"ᴍᴀxɪᴍᴜᴍ ᴀʟʟᴏᴡᴇᴅ: <b>{max_concurrent}</b>\n\n"
                "ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ ғᴏʀ ᴄᴜʀʀᴇɴᴛ ᴅᴏᴡɴʟᴏᴀᴅs ᴛᴏ ᴄᴏᴍᴘʟᴇᴛᴇ.",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Generate unique download ID
        global download_counter
        download_counter += 1
        download_id = download_counter
        
        # Add to active downloads
        progress_tracker = add_active_download(user_id, download_id, url)
        
        # Send initial status message
        status_msg = await message.reply_text(
            f"<b>🔄 ɪɴɪᴛɪᴀʟɪᴢɪɴɢ ᴅᴏᴡɴʟᴏᴀᴅ...</b>\n\n"
            f"<b>🆔 ᴅᴏᴡɴʟᴏᴀᴅ:</b> #{download_id}\n"
            f"<b>🌐 ᴜʀʟ:</b> <code>{url[:50]}{'...' if len(url) > 50 else ''}</code>\n"
            f"<b>📊 ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅs:</b> {current_downloads + 1}",
            parse_mode=ParseMode.HTML
        )
        
        print(f"🚀 Starting download {download_id} for user {user_id}: {url}")
        
        # Start download in background
        asyncio.create_task(download_and_send(client, message, status_msg, url, user_id, download_id))
        
    except Exception as e:
        print(f"❌ Error handling URL: {e}")
        await message.reply_text(
            "<b>❌ ᴇʀʀᴏʀ ᴘʀᴏᴄᴇssɪɴɢ ʀᴇǫᴜᴇsᴛ!</b>",
            parse_mode=ParseMode.HTML
        )

@Client.on_message(filters.command("downloads") & filters.private)
async def show_downloads_command(client: Client, message: Message):
    """Show user's active downloads"""
    try:
        user_id = message.from_user.id
        
        if user_id not in active_downloads or not active_downloads[user_id]:
            await message.reply_text(
                "<b>📥 ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅs</b>\n\n"
                "❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅs ғᴏᴜɴᴅ.",
                parse_mode=ParseMode.HTML
            )
            return
        
        downloads_text = "<b>📥 ʏᴏᴜʀ ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅs</b>\n\n"
        
        for i, tracker in enumerate(active_downloads[user_id], 1):
            # Calculate progress
            if tracker.total_size > 0:
                progress_percent = (tracker.downloaded / tracker.total_size) * 100
            else:
                progress_percent = 0
            
            # Format filename
            filename = tracker.filename
            if len(filename) > 25:
                filename = filename[:22] + "..."
            
            # Format URL
            url_display = tracker.url
            if len(url_display) > 30:
                url_display = url_display[:27] + "..."
            
            downloads_text += (
                f"<b>{i}. ᴅᴏᴡɴʟᴏᴀᴅ #{tracker.download_id}</b>\n"
                f"   📁 <code>{filename}</code>\n"
                f"   📊 {progress_percent:.1f}% • {tracker.status}\n"
                f"   🌐 <code>{url_display}</code>\n"
                f"   ⚡ {format_bytes(tracker.speed)}/s\n\n"
            )
        
        downloads_text += f"<b>📈 ᴛᴏᴛᴀʟ ᴀᴄᴛɪᴠᴇ:</b> {len(active_downloads[user_id])}"
        
        await message.reply_text(downloads_text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        print(f"❌ Error in downloads command: {e}")
        await message.reply_text(
            "<b>❌ ᴇʀʀᴏʀ ʟᴏᴀᴅɪɴɢ ᴅᴏᴡɴʟᴏᴀᴅs!</b>",
            parse_mode=ParseMode.HTML
        )

@Client.on_message(filters.command("cancel") & filters.private)
async def cancel_download_command(client: Client, message: Message):
    """Cancel a specific download"""
    try:
        user_id = message.from_user.id
        
        # Parse command
        command_parts = message.text.split()
        if len(command_parts) < 2:
            await message.reply_text(
                "<b>📝 ᴜsᴀɢᴇ:</b>\n\n"
                "<code>/cancel [download_id]</code>\n\n"
                "<b>ᴇxᴀᴍᴘʟᴇ:</b>\n"
                "<code>/cancel 123</code>\n\n"
                "ᴜsᴇ /downloads ᴛᴏ sᴇᴇ ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅ ɪᴅs.",
                parse_mode=ParseMode.HTML
            )
            return
        
        try:
            download_id = int(command_parts[1])
        except ValueError:
            await message.reply_text(
                "❌ <b>ɪɴᴠᴀʟɪᴅ ᴅᴏᴡɴʟᴏᴀᴅ ɪᴅ!</b>\n\n"
                "ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ.",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Find and remove the download
        tracker = get_download_tracker(user_id, download_id)
        if not tracker:
            await message.reply_text(
                f"❌ <b>ᴅᴏᴡɴʟᴏᴀᴅ #{download_id} ɴᴏᴛ ғᴏᴜɴᴅ!</b>\n\n"
                "ᴜsᴇ /downloads ᴛᴏ sᴇᴇ ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅs.",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Remove from active downloads
        remove_active_download(user_id, download_id)
        
        # Clean up files
        cleanup_files(f"./downloads/{user_id}_{download_id}/")
        
        await message.reply_text(
            f"✅ <b>ᴅᴏᴡɴʟᴏᴀᴅ #{download_id} ᴄᴀɴᴄᴇʟʟᴇᴅ!</b>\n\n"
            f"ғɪʟᴇs ʜᴀᴠᴇ ʙᴇᴇɴ ᴄʟᴇᴀɴᴇᴅ ᴜᴘ.",
            parse_mode=ParseMode.HTML
        )
        
        print(f"🚫 Download {download_id} cancelled by user {user_id}")
        
    except Exception as e:
        print(f"❌ Error in cancel command: {e}")
        await message.reply_text(
            "❌ <b>ᴇʀʀᴏʀ ᴄᴀɴᴄᴇʟʟɪɴɢ ᴅᴏᴡɴʟᴏᴀᴅ!</b>",
            parse_mode=ParseMode.HTML
        )

@Client.on_message(filters.command("stats") & filters.private)
async def stats_command(client: Client, message: Message):
    """Handle /stats command with database integration"""
    try:
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
            f"<b>💾 ᴍᴀx ғɪʟᴇ sɪᴢᴇ:</b> 2ɢʙ\n"
            f"<b>🔢 ᴍᴀx ᴄᴏɴᴄᴜʀʀᴇɴᴛ:</b> 3 ᴘᴇʀ ᴜsᴇʀ\n\n"
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


@Client.on_message(filters.command("history") & filters.private)
async def history_command(client: Client, message: Message):
    """Show user's download history"""
    try:
        user_id = message.from_user.id
        username = message.from_user.first_name or message.from_user.username or "Unknown"
        
        # Register/update user
        await register_new_user(user_id, username, message.from_user.first_name or "")
        
        # Get download history from database
        history = await get_user_download_history(user_id, 20)
        
        if not history:
            await message.reply_text(
                "<b>📋 ᴅᴏᴡɴʟᴏᴀᴅ ʜɪsᴛᴏʀʏ</b>\n\n"
                "<b>❌ ɴᴏ ᴅᴏᴡɴʟᴏᴀᴅs ғᴏᴜɴᴅ</b>\n\n"
                "sᴛᴀʀᴛ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ᴛᴏ sᴇᴇ ʏᴏᴜʀ ʜɪsᴛᴏʀʏ!",
                parse_mode=ParseMode.HTML
            )
            return
        
        history_text = f"<b>📋 ʏᴏᴜʀ ᴅᴏᴡɴʟᴏᴀᴅ ʜɪsᴛᴏʀʏ</b>\n\n"
        
        for i, item in enumerate(history, 1):
            date = item.get('download_time', datetime.now()).strftime('%Y-%m-%d %H:%M')
            site = item.get('site', 'Unknown')
            file_size = format_bytes(item.get('file_size', 0))
            file_type = item.get('file_type', 'unknown')
            file_name = item.get('file_name', 'Unknown File')
            
            # Truncate long URLs
            url = item.get('url', 'Unknown')
            if len(url) > 40:
                url = url[:37] + "..."
            
            # Truncate long file names
            if len(file_name) > 30:
                file_name = file_name[:27] + "..."
            
            history_text += f"<b>{i}.</b> <code>{date}</code>\n"
            history_text += f"   📁 <code>{file_name}</code>\n"
            history_text += f"   🌐 {site} • 📦 {file_size} • 📄 {file_type}\n"
            history_text += f"   🔗 <code>{url}</code>\n\n"
            
            # Limit message length
            if len(history_text) > 3500:
                history_text += f"<i>... ᴀɴᴅ {len(history) - i} ᴍᴏʀᴇ</i>"
                break
        
        # Add summary at the end
        total_downloads = len(history)
        total_size = sum(item.get('file_size', 0) for item in history)
        history_text += f"<b>📊 sᴜᴍᴍᴀʀʏ:</b> {total_downloads} downloads • {format_bytes(total_size)}"
        
        await message.reply_text(history_text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        print(f"❌ Error in history command: {e}")
        await message.reply_text(
            "<b>❌ ᴇʀʀᴏʀ ʟᴏᴀᴅɪɴɢ ʜɪsᴛᴏʀʏ</b>",
            parse_mode=ParseMode.HTML
        )

@Client.on_message(filters.command("leaderboard") & filters.private)
async def leaderboard_command(client: Client, message: Message):
    """Show top users leaderboard"""
    try:
        user_id = message.from_user.id
        username = message.from_user.first_name or message.from_user.username or "Unknown"
        
        # Register/update user
        await register_new_user(user_id, username, message.from_user.first_name or "")
        
        # Get top users from database
        top_users = await get_top_users(10)
        
        if not top_users:
            await message.reply_text(
                "<b>🏆 ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ</b>\n\n"
                "<b>❌ ɴᴏ ᴅᴀᴛᴀ ᴀᴠᴀɪʟᴀʙʟᴇ</b>\n\n"
                "sᴛᴀʀᴛ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ᴛᴏ sᴇᴇ ᴛʜᴇ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ!",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Get current user's rank
        user_rank = await get_user_rank(user_id)
        current_user = await get_user(user_id)
        
        leaderboard_text = f"<b>🏆 ᴛᴏᴘ ᴅᴏᴡɴʟᴏᴀᴅᴇʀs</b>\n\n"
        
        medals = ["🥇", "🥈", "🥉"]
        
        for i, user in enumerate(top_users, 1):
            username_display = user.get('username', user.get('first_name', 'Unknown'))
            downloads = user.get('total_downloads', 0)
            total_size = format_bytes(user.get('total_size', 0))
            
            # Truncate long usernames
            if len(username_display) > 15:
                username_display = username_display[:12] + "..."
            
            medal = medals[i-1] if i <= 3 else f"{i}."
            
            # Highlight current user
            if user.get('_id') == user_id:
                leaderboard_text += f"<b>➤ {medal} {username_display}</b>\n"
                leaderboard_text += f"   📈 {downloads:,} downloads • 💾 {total_size}\n\n"
            else:
                leaderboard_text += f"{medal} <b>{username_display}</b>\n"
                leaderboard_text += f"   📈 {downloads:,} downloads • 💾 {total_size}\n\n"
        
        # Show current user's rank if not in top 10
        if user_rank > 10:
            username_display = current_user.get('username', current_user.get('first_name', 'You'))
            downloads = current_user.get('total_downloads', 0)
            total_size = format_bytes(current_user.get('total_size', 0))
            
            leaderboard_text += f"<b>━━━━━━━━━━━━━━━━━━━━</b>\n"
            leaderboard_text += f"<b>➤ #{user_rank} {username_display}</b>\n"
            leaderboard_text += f"   📈 {downloads:,} downloads • 💾 {total_size}\n\n"
        
        # Add additional stats
        leaderboard_text += f"<i>ʏᴏᴜʀ ʀᴀɴᴋ: #{user_rank}</i>\n"
        leaderboard_text += f"<i>ʏᴏᴜʀ ᴅᴏᴡɴʟᴏᴀᴅs: {current_user.get('total_downloads', 0):,}</i>"
        
        await message.reply_text(leaderboard_text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        print(f"❌ Error in leaderboard command: {e}")
        await message.reply_text(
            "<b>❌ ᴇʀʀᴏʀ ʟᴏᴀᴅɪɴɢ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ</b>",
            parse_mode=ParseMode.HTML
        )

@Client.on_message(filters.command("clearall") & filters.private)
async def clear_all_downloads_command(client: Client, message: Message):
    """Clear all active downloads for user (emergency command)"""
    try:
        user_id = message.from_user.id
        
        if user_id not in active_downloads or not active_downloads[user_id]:
            await message.reply_text(
                "❌ <b>ɴᴏ ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅs ғᴏᴜɴᴅ!</b>",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Get count before clearing
        download_count = len(active_downloads[user_id])
        
        # Clear all downloads for user
        for tracker in active_downloads[user_id]:
            cleanup_files(f"./downloads/{user_id}_{tracker.download_id}/")
        
        # Remove from active downloads
        del active_downloads[user_id]
        
        await message.reply_text(
            f"✅ <b>ᴀʟʟ ᴅᴏᴡɴʟᴏᴀᴅs ᴄʟᴇᴀʀᴇᴅ!</b>\n\n"
            f"<b>📊 ᴄʟᴇᴀʀᴇᴅ:</b> {download_count} ᴅᴏᴡɴʟᴏᴀᴅs\n"
            f"<b>🗑️ ғɪʟᴇs:</b> ᴄʟᴇᴀɴᴇᴅ ᴜᴘ",
            parse_mode=ParseMode.HTML
        )
        
        print(f"🧹 Cleared all downloads for user {user_id} ({download_count} downloads)")
        
    except Exception as e:
        print(f"❌ Error in clearall command: {e}")
        await message.reply_text(
            "❌ <b>ᴇʀʀᴏʀ ᴄʟᴇᴀʀɪɴɢ ᴅᴏᴡɴʟᴏᴀᴅs!</b>",
            parse_mode=ParseMode.HTML
        )

@Client.on_message(filters.command("speedtest") & filters.private)
async def speedtest_command(client: Client, message: Message):
    """Test bot response speed"""
    try:
        import time
        start_time = time.time()
        
        # Send initial message
        sent_message = await message.reply_text("🏃‍♂️ ᴛᴇsᴛɪɴɢ sᴘᴇᴇᴅ...")
        
        # Calculate response time
        end_time = time.time()
        response_time = (end_time - start_time) * 1000  # Convert to milliseconds
        
        # Get system stats
        user_id = message.from_user.id
        total_active = sum(len(downloads) for downloads in active_downloads.values())
        user_active = get_active_download_count(user_id)
        
        # Update with final response
        speed_text = (
            f"🏃‍♂️ <b>sᴘᴇᴇᴅ ᴛᴇsᴛ ʀᴇsᴜʟᴛs</b>\n\n"
            f"⚡ <b>ʀᴇsᴘᴏɴsᴇ ᴛɪᴍᴇ:</b> <code>{response_time:.2f}ᴍs</code>\n"
            f"🔄 <b>ʏᴏᴜʀ ᴀᴄᴛɪᴠᴇ:</b> {user_active} ᴅᴏᴡɴʟᴏᴀᴅs\n"
            f"🌐 <b>ᴛᴏᴛᴀʟ ᴀᴄᴛɪᴠᴇ:</b> {total_active} ᴅᴏᴡɴʟᴏᴀᴅs\n"
            f"🤖 <b>sᴛᴀᴛᴜs:</b> {'🟢 ᴇxᴄᴇʟʟᴇɴᴛ' if response_time < 100 else '🟡 ɢᴏᴏᴅ' if response_time < 500 else '🔴 sʟᴏᴡ'}"
        )
        
        await sent_message.edit_text(speed_text, parse_mode=ParseMode.HTML)
        print(f"🏃‍♂️ SPEEDTEST: {user_id} - {response_time:.2f}ms")
        
    except Exception as e:
        print(f"❌ Error in speedtest command: {e}")
        await message.reply_text(
            "❌ <b>sᴘᴇᴇᴅ ᴛᴇsᴛ ғᴀɪʟᴇᴅ!</b>", 
            parse_mode=ParseMode.HTML
        )

# Admin commands for managing downloads
@Client.on_message(filters.command("globalstats") & filters.private)
async def global_stats_command(client: Client, message: Message):
    """Show global download statistics (Admin only)"""
    try:
        user_id = message.from_user.id
        
        # Check if user is admin (you can define ADMIN_IDS in config)
        ADMIN_IDS = [7560922302]  # Add your admin IDs here
        if user_id not in ADMIN_IDS:
            await message.reply_text("❌ <b>ᴀᴅᴍɪɴ ᴏɴʟʏ ᴄᴏᴍᴍᴀɴᴅ!</b>", parse_mode=ParseMode.HTML)
            return
        
        # Get global stats
        total_active = sum(len(downloads) for downloads in active_downloads.values())
        total_users_with_downloads = len(active_downloads)
        
        # Get database stats
        stats = await get_stats()
        user_count = await get_user_count()
        
        global_text = (
            f"<b>🌐 ɢʟᴏʙᴀʟ sᴛᴀᴛɪsᴛɪᴄs</b>\n\n"
            f"<b>📊 ᴅᴀᴛᴀʙᴀsᴇ:</b>\n"
            f"• ᴛᴏᴛᴀʟ ᴜsᴇʀs: {user_count:,}\n"
            f"• ᴛᴏᴛᴀʟ ᴅᴏᴡɴʟᴏᴀᴅs: {stats.get('total_downloads', 0):,}\n\n"
            f"<b>🔄 ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅs:</b>\n"
            f"• ᴛᴏᴛᴀʟ ᴀᴄᴛɪᴠᴇ: {total_active}\n"
            f"• ᴀᴄᴛɪᴠᴇ ᴜsᴇʀs: {total_users_with_downloads}\n\n"
        )
        
        # Show per-user breakdown
        if active_downloads:
            global_text += "<b>👥 ᴀᴄᴛɪᴠᴇ ᴜsᴇʀs:</b>\n"
            for uid, downloads in list(active_downloads.items())[:10]:  # Show top 10
                global_text += f"• {uid}: {len(downloads)} ᴅᴏᴡɴʟᴏᴀᴅs\n"
            
            if len(active_downloads) > 10:
                global_text += f"• ... ᴀɴᴅ {len(active_downloads) - 10} ᴍᴏʀᴇ\n"
        
        await message.reply_text(global_text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        print(f"❌ Error in globalstats command: {e}")
        await message.reply_text(
            "❌ <b>ᴇʀʀᴏʀ ʟᴏᴀᴅɪɴɢ ɢʟᴏʙᴀʟ sᴛᴀᴛs!</b>",
            parse_mode=ParseMode.HTML
        )

@Client.on_message(filters.command("clearuser") & filters.private)
async def clear_user_downloads_command(client: Client, message: Message):
    """Clear downloads for specific user (Admin only)"""
    try:
        user_id = message.from_user.id
        
        # Check if user is admin
        ADMIN_IDS = [7560922302]  # Add your admin IDs here
        if user_id not in ADMIN_IDS:
            await message.reply_text("❌ <b>ᴀᴅᴍɪɴ ᴏɴʟʏ ᴄᴏᴍᴍᴀɴᴅ!</b>", parse_mode=ParseMode.HTML)
            return
        
        # Parse command
        command_parts = message.text.split()
        if len(command_parts) < 2:
            await message.reply_text(
                "<b>📝 ᴜsᴀɢᴇ:</b>\n\n"
                "<code>/clearuser [user_id]</code>\n\n"
                "<b>ᴇxᴀᴍᴘʟᴇ:</b>\n"
                "<code>/clearuser 123456789</code>",
                parse_mode=ParseMode.HTML
            )
            return
        
        try:
            target_user_id = int(command_parts[1])
        except ValueError:
            await message.reply_text(
                "❌ <b>ɪɴᴠᴀʟɪᴅ ᴜsᴇʀ ɪᴅ!</b>",
                parse_mode=ParseMode.HTML
            )
            return
        
        if target_user_id not in active_downloads or not active_downloads[target_user_id]:
            await message.reply_text(
                f"❌ <b>ɴᴏ ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅs ғᴏʀ ᴜsᴇʀ {target_user_id}!</b>",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Clear downloads for target user
        download_count = len(active_downloads[target_user_id])
        
        for tracker in active_downloads[target_user_id]:
            cleanup_files(f"./downloads/{target_user_id}_{tracker.download_id}/")
        
        del active_downloads[target_user_id]
        
        await message.reply_text(
            f"✅ <b>ᴄʟᴇᴀʀᴇᴅ ᴅᴏᴡɴʟᴏᴀᴅs!</b>\n\n"
            f"<b>👤 ᴜsᴇʀ:</b> {target_user_id}\n"
            f"<b>📊 ᴄʟᴇᴀʀᴇᴅ:</b> {download_count} ᴅᴏᴡɴʟᴏᴀᴅs",
            parse_mode=ParseMode.HTML
        )
        
        print(f"🧹 Admin {user_id} cleared downloads for user {target_user_id}")
        
    except Exception as e:
        print(f"❌ Error in clearuser command: {e}")
        await message.reply_text(
            "❌ <b>ᴇʀʀᴏʀ ᴄʟᴇᴀʀɪɴɢ ᴜsᴇʀ ᴅᴏᴡɴʟᴏᴀᴅs!</b>",
            parse_mode=ParseMode.HTML
        )

# Cleanup function to run periodically
async def cleanup_stale_downloads():
    """Clean up downloads that have been running too long"""
    try:
        current_time = time.time()
        stale_threshold = 3600  # 1 hour
        
        users_to_clean = []
        
        for user_id, downloads in active_downloads.items():
            stale_downloads = []
            
            for tracker in downloads:
                if current_time - tracker.start_time > stale_threshold:
                    stale_downloads.append(tracker)
            
            # Remove stale downloads
            for tracker in stale_downloads:
                cleanup_files(f"./downloads/{user_id}_{tracker.download_id}/")
                downloads.remove(tracker)
                print(f"🧹 Cleaned up stale download {tracker.download_id} for user {user_id}")
            
            # Mark empty user lists for removal
            if not downloads:
                users_to_clean.append(user_id)
        
        # Remove empty user entries
        for user_id in users_to_clean:
            del active_downloads[user_id]
        
        if users_to_clean or any(stale_downloads for downloads in active_downloads.values()):
            print(f"🧹 Cleanup completed: {len(users_to_clean)} users cleaned")
            
    except Exception as e:
        print(f"❌ Error in cleanup: {e}")

@Client.on_message(filters.command("cleanup") & filters.private)
async def cleanup_command(client: Client, message: Message):
    """Clean up download directories and temporary files (Admin only)"""
    try:
        user_id = message.from_user.id
        
        # Check if user is admin
        ADMIN_IDS = [7560922302]  # Add your admin IDs here
        if user_id not in ADMIN_IDS:
            await message.reply_text("❌ <b>ᴀᴅᴍɪɴ ᴏɴʟʏ ᴄᴏᴍᴍᴀɴᴅ!</b>", parse_mode=ParseMode.HTML)
            return
        
        # Parse command arguments
        command_parts = message.text.split()
        cleanup_type = "all"  # default
        
        if len(command_parts) > 1:
            cleanup_type = command_parts[1].lower()
        
        # Send initial status
        status_msg = await message.reply_text(
            "<b>🧹 sᴛᴀʀᴛɪɴɢ ᴄʟᴇᴀɴᴜᴘ...</b>",
            parse_mode=ParseMode.HTML
        )
        
        cleaned_files = 0
        cleaned_dirs = 0
        freed_space = 0
        
        if cleanup_type in ["all", "downloads"]:
            # Clean download directories
            downloads_path = "./downloads/"
            if os.path.exists(downloads_path):
                for item in os.listdir(downloads_path):
                    item_path = os.path.join(downloads_path, item)
                    try:
                        if os.path.isfile(item_path):
                            file_size = os.path.getsize(item_path)
                            os.remove(item_path)
                            cleaned_files += 1
                            freed_space += file_size
                        elif os.path.isdir(item_path):
                            # Clean directory contents
                            for root, dirs, files in os.walk(item_path, topdown=False):
                                for file in files:
                                    file_path = os.path.join(root, file)
                                    try:
                                        file_size = os.path.getsize(file_path)
                                        os.remove(file_path)
                                        cleaned_files += 1
                                        freed_space += file_size
                                    except Exception as e:
                                        print(f"Error removing file {file_path}: {e}")
                                
                                for dir in dirs:
                                    dir_path = os.path.join(root, dir)
                                    try:
                                        os.rmdir(dir_path)
                                        cleaned_dirs += 1
                                    except Exception as e:
                                        print(f"Error removing dir {dir_path}: {e}")
                            
                            # Remove the main directory
                            try:
                                os.rmdir(item_path)
                                cleaned_dirs += 1
                            except Exception as e:
                                print(f"Error removing main dir {item_path}: {e}")
                                
                    except Exception as e:
                        print(f"Error processing {item_path}: {e}")
        
        if cleanup_type in ["all", "temp"]:
            # Clean temporary files
            temp_patterns = ["*.tmp", "*.temp", "*.part", "*.ytdl"]
            for pattern in temp_patterns:
                import glob
                for temp_file in glob.glob(pattern):
                    try:
                        file_size = os.path.getsize(temp_file)
                        os.remove(temp_file)
                        cleaned_files += 1
                        freed_space += file_size
                    except Exception as e:
                        print(f"Error removing temp file {temp_file}: {e}")
        
        if cleanup_type in ["all", "logs"]:
            # Clean old log files (if any)
            log_patterns = ["*.log", "*.log.*"]
            for pattern in log_patterns:
                import glob
                for log_file in glob.glob(pattern):
                    try:
                        # Only remove if older than 7 days
                        if os.path.getmtime(log_file) < time.time() - (7 * 24 * 60 * 60):
                            file_size = os.path.getsize(log_file)
                            os.remove(log_file)
                            cleaned_files += 1
                            freed_space += file_size
                    except Exception as e:
                        print(f"Error removing log file {log_file}: {e}")
        
        # Format freed space
        def format_size(size_bytes):
            if size_bytes == 0:
                return "0 B"
            size_names = ["B", "KB", "MB", "GB", "TB"]
            import math
            i = int(math.floor(math.log(size_bytes, 1024)))
            p = math.pow(1024, i)
            s = round(size_bytes / p, 2)
            return f"{s} {size_names[i]}"
        
        # Update status with results
        cleanup_text = (
            f"<b>✅ ᴄʟᴇᴀɴᴜᴘ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!</b>\n\n"
            f"<b>🗑️ ᴄʟᴇᴀɴᴇᴅ:</b>\n"
            f"• {cleaned_files:,} ғɪʟᴇs\n"
            f"• {cleaned_dirs:,} ᴅɪʀᴇᴄᴛᴏʀɪᴇs\n"
            f"• {format_size(freed_space)} ғʀᴇᴇᴅ\n\n"
            f"<b>🧹 ᴛʏᴘᴇ:</b> {cleanup_type}\n"
            f"<b>⏰ ᴛɪᴍᴇ:</b> {datetime.now().strftime('%H:%M:%S')}"
        )
        
        await status_msg.edit_text(cleanup_text, parse_mode=ParseMode.HTML)
        
        print(f"🧹 Admin {user_id} performed cleanup: {cleaned_files} files, {cleaned_dirs} dirs, {format_size(freed_space)} freed")
        
    except Exception as e:
        print(f"❌ Error in cleanup command: {e}")
        import traceback
        traceback.print_exc()
        await message.reply_text(
            "❌ <b>ᴄʟᴇᴀɴᴜᴘ ғᴀɪʟᴇᴅ!</b>",
            parse_mode=ParseMode.HTML
        )

# Start cleanup task
async def start_cleanup_task():
    """Start the periodic cleanup task"""
    while True:
        try:
            await asyncio.sleep(1800)  # Run every 30 minutes
            await cleanup_stale_downloads()
        except Exception as e:
            print(f"❌ Cleanup task error: {e}")
            await asyncio.sleep(300)  # Wait 5 minutes before retrying

# Initialize cleanup task when bot starts
asyncio.create_task(start_cleanup_task())

print("✅ Multiple download system initialized!")
print("📊 Features:")
print("   • Up to 3 concurrent downloads per user")
print("   • Unique download IDs for tracking")
print("   • Progress tracking for each download")
print("   • File splitting for large files")
print("   • Database integration for stats")
print("   • Automatic cleanup of stale downloads")
print("   • Admin commands for management")
