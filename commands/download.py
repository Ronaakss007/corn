
import os
import re
import time
import asyncio
import yt_dlp
import aiohttp
import re
import requests
from urllib.parse import urlparse, parse_qs
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

# ==================== GOOGLE DRIVE FUNCTIONS ====================

def extract_gdrive_file_id(url):
    """Extract file ID from Google Drive URL"""
    try:
        # Pattern 1: https://drive.google.com/file/d/FILE_ID/view
        pattern1 = r'/file/d/([a-zA-Z0-9-_]+)'
        match1 = re.search(pattern1, url)
        if match1:
            return match1.group(1)
        
        # Pattern 2: https://drive.google.com/open?id=FILE_ID
        pattern2 = r'[?&]id=([a-zA-Z0-9-_]+)'
        match2 = re.search(pattern2, url)
        if match2:
            return match2.group(1)
        
        # Pattern 3: https://drive.google.com/uc?id=FILE_ID
        pattern3 = r'[?&]id=([a-zA-Z0-9-_]+)'
        match3 = re.search(pattern3, url)
        if match3:
            return match3.group(1)
            
        return None
    except Exception as e:
        print(f"Error extracting Google Drive file ID: {e}")
        return None

async def get_gdrive_file_info(file_id):
    """Get Google Drive file information"""
    try:
        # Use the export/download URL to get file info
        info_url = f"https://drive.google.com/file/d/{file_id}/view"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(info_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            # Extract filename from page content
            filename_pattern = r'"title":"([^"]+)"'
            filename_match = re.search(filename_pattern, response.text)
            filename = filename_match.group(1) if filename_match else f"gdrive_file_{file_id}"
            
            # Try to get file size (this might not always work)
            size_pattern = r'"size":"(\d+)"'
            size_match = re.search(size_pattern, response.text)
            file_size = int(size_match.group(1)) if size_match else 0
            
            return {
                'filename': filename,
                'file_size': file_size,
                'file_id': file_id
            }
        
        return None
        
    except Exception as e:
        print(f"Error getting Google Drive file info: {e}")
        return None

async def download_gdrive_file(file_id, download_path, progress_tracker):
    """Download file from Google Drive"""
    try:
        # Try direct download first
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        session = requests.Session()
        response = session.get(download_url, headers=headers, stream=True, timeout=30)
        
        # Check if we need to handle the "large file" confirmation
        if 'confirm=' in response.text or 'download_warning' in response.text:
            # Extract confirmation token
            confirm_pattern = r'confirm=([^&]+)'
            confirm_match = re.search(confirm_pattern, response.text)
            
            if confirm_match:
                confirm_token = confirm_match.group(1)
                download_url = f"https://drive.google.com/uc?export=download&confirm={confirm_token}&id={file_id}"
                response = session.get(download_url, headers=headers, stream=True, timeout=30)
            else:
                # Try alternative method for large files
                confirm_url = f"https://drive.google.com/uc?export=download&id={file_id}&confirm=t"
                response = session.get(confirm_url, headers=headers, stream=True, timeout=30)
        
        if response.status_code != 200:
            print(f"Failed to download Google Drive file: HTTP {response.status_code}")
            return False
        
        # Get filename from Content-Disposition header if available
        content_disposition = response.headers.get('Content-Disposition', '')
        if 'filename=' in content_disposition:
            filename_match = re.search(r'filename="([^"]+)"', content_disposition)
            if filename_match:
                filename = filename_match.group(1)
            else:
                filename = f"gdrive_file_{file_id}"
        else:
            filename = f"gdrive_file_{file_id}"
        
        # Ensure download directory exists
        os.makedirs(os.path.dirname(download_path), exist_ok=True)
        
        # Get total file size
        total_size = int(response.headers.get('Content-Length', 0))
        progress_tracker.total_size = total_size
        progress_tracker.filename = os.path.join(download_path, filename)
        progress_tracker.status = "ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ"
        
        # Download the file
        file_path = os.path.join(download_path, filename)
        downloaded = 0
        
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    progress_tracker.downloaded = downloaded
                    
                    # Calculate speed
                    elapsed_time = time.time() - progress_tracker.start_time
                    if elapsed_time > 0:
                        progress_tracker.speed = downloaded / elapsed_time
        
        progress_tracker.status = "ᴄᴏᴍᴘʟᴇᴛᴇᴅ"
        return True
        
    except Exception as e:
        print(f"Error downloading Google Drive file: {e}")
        progress_tracker.status = f"ᴇʀʀᴏʀ: {str(e)}"
        return False

def is_gdrive_url(url):
    """Check if URL is a Google Drive link"""
    gdrive_patterns = [
        r'drive\.google\.com',
        r'docs\.google\.com',
    ]
    
    return any(re.search(pattern, url.lower()) for pattern in gdrive_patterns)


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
    
def download_gdrive_file(file_id, download_path, progress_tracker):
    """Download file from Google Drive (synchronous version)"""
    try:
        # Try direct download first
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        session = requests.Session()
        response = session.get(download_url, headers=headers, stream=True, timeout=30)
        
        # Check if we need to handle the "large file" confirmation
        if 'confirm=' in response.text or 'download_warning' in response.text:
            # Extract confirmation token
            confirm_pattern = r'confirm=([^&]+)'
            confirm_match = re.search(confirm_pattern, response.text)
            
            if confirm_match:
                confirm_token = confirm_match.group(1)
                download_url = f"https://drive.google.com/uc?export=download&confirm={confirm_token}&id={file_id}"
                response = session.get(download_url, headers=headers, stream=True, timeout=30)
            else:
                # Try alternative method for large files
                confirm_url = f"https://drive.google.com/uc?export=download&id={file_id}&confirm=t"
                response = session.get(confirm_url, headers=headers, stream=True, timeout=30)
        
        if response.status_code != 200:
            print(f"Failed to download Google Drive file: HTTP {response.status_code}")
            return False
        
        # Get filename from Content-Disposition header if available
        content_disposition = response.headers.get('Content-Disposition', '')
        if 'filename=' in content_disposition:
            filename_match = re.search(r'filename="([^"]+)"', content_disposition)
            if filename_match:
                filename = filename_match.group(1)
            else:
                filename = f"gdrive_file_{file_id}"
        else:
            # Try to get filename from progress_tracker metadata
            if hasattr(progress_tracker, 'metadata') and progress_tracker.metadata:
                filename = progress_tracker.metadata.get('filename', f"gdrive_file_{file_id}")
            else:
                filename = f"gdrive_file_{file_id}"
        
        # Ensure download directory exists
        os.makedirs(download_path, exist_ok=True)
        
        # Get total file size
        total_size = int(response.headers.get('Content-Length', 0))
        if total_size > 0:
            progress_tracker.total_size = total_size
        
        progress_tracker.filename = os.path.join(download_path, filename)
        progress_tracker.status = "ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ"
        
        # Download the file
        file_path = os.path.join(download_path, filename)
        downloaded = 0
        
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    progress_tracker.downloaded = downloaded
                    
                    # Calculate speed
                    elapsed_time = time.time() - progress_tracker.start_time
                    if elapsed_time > 0:
                        progress_tracker.speed = downloaded / elapsed_time
        
        progress_tracker.status = "ᴄᴏᴍᴘʟᴇᴛᴇᴅ"
        print(f"Successfully downloaded Google Drive file: {filename}")
        return True
        
    except Exception as e:
        print(f"Error downloading Google Drive file: {e}")
        progress_tracker.status = f"ᴇʀʀᴏʀ: {str(e)}"
        return False

# ==================== UPLOAD TO USER FIRST ====================

async def upload_to_user_first(client, message, file_path, progress_tracker):
    """Upload file to user first with spoiler support for videos"""
    try:
        if not os.path.exists(file_path):
            print(f"File does not exist: {file_path}")
            return None
            
        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        status_msg = progress_tracker.status_msg
        
        print(f"upload_to_user_first called for: {file_name}")
        print(f"File size: {file_size} bytes")
        
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
                # Import splitting functions
                if is_video_file(file_path):
                    print("Splitting as video file")
                    try:
                        from helper_func import split_video
                        file_chunks = await split_video(file_path)
                    except ImportError:
                        print("split_video not available, using generic split")
                        from helper_func import split_file
                        file_chunks = await split_file(file_path) if asyncio.iscoroutinefunction(split_file) else split_file(file_path)
                else:
                    print("Splitting as regular file")
                    from helper_func import split_file
                    file_chunks = await split_file(file_path) if asyncio.iscoroutinefunction(split_file) else split_file(file_path)
                
                if not file_chunks:
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
                    
                    chunk_msg = await upload_single_file_to_user(client, message, chunk_path, progress_tracker, i, len(file_chunks))
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
                
                # Return ALL uploaded messages for dump channel copying
                return uploaded_messages if uploaded_messages else None
                
            except Exception as split_error:
                print(f"Splitting error: {split_error}")
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
            return await upload_single_file_to_user(client, message, file_path, progress_tracker)
            
    except Exception as main_error:
        print(f"upload_to_user_first main error: {main_error}")
        try:
            await status_msg.edit_text(
                f"<b>❌ ᴜᴘʟᴏᴀᴅ ғᴀɪʟᴇᴅ!</b>\n\n"
                f"<b>📁 ғɪʟᴇ:</b> <code>{file_name[:50] if 'file_name' in locals() else 'Unknown'}{'...' if 'file_name' in locals() and len(file_name) > 50 else ''}</code>\n"
                f"<b>❌ ᴇʀʀᴏʀ:</b> <code>{str(main_error)[:100]}</code>",
                parse_mode=ParseMode.HTML
            )
        except Exception as edit_error:
            print(f"Failed to edit status message: {edit_error}")
        return None


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
                print(f"Failed to copy to dump channel {dump_id}: {e}")
                pass  # Continue with other dump channels if one fails
                
    except Exception as e:
        print(f"Error in copy_to_dumps: {e}")
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
        print(f"Progress update error: {e}")
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
        print(f"Upload progress update error: {e}")
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

def sanitize_filename(filename):
    """Sanitize filename for better compatibility"""
    import re
    
    # Remove or replace problematic characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Replace multiple spaces with single space
    filename = re.sub(r'\s+', ' ', filename)
    
    # Remove leading/trailing spaces and dots
    filename = filename.strip(' .')
    
    # Limit filename length (keep extension)
    name, ext = os.path.splitext(filename)
    if len(name) > 200:  # Leave room for extension and path
        name = name[:200]
    
    return name + ext

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
