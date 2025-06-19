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
MAX_CONCURRENT_DOWNLOADS = 5  # Reduced from 10 to prevent rate limiting
UPLOAD_SEMAPHORE = asyncio.Semaphore(2)  # Limit concurrent uploads

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
        self.last_update = 0  # Track last progress update time

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
        
        # Extract metadata with error handling
        try:
            metadata = await get_video_metadata_safe(url)
            if metadata:
                progress_tracker.metadata = metadata
        except Exception as e:
            print(f"❌ Error getting video metadata: {str(e)}")
        
        # Start download in background
        asyncio.create_task(download_and_send_concurrent(client, message, progress_tracker, user_id))
        
    except Exception as e:
        await message.reply_text(
            f"<b>❌ ᴇʀʀᴏʀ</b>\n\n<code>{str(e)}</code>",
            parse_mode=ParseMode.HTML
        )
        # Clean up on error
        if 'user_id' in locals() and 'download_id' in locals():
            if user_id in active_downloads:
                active_downloads[user_id] = [t for t in active_downloads[user_id] if t.download_id != download_id]
                if not active_downloads[user_id]:
                    del active_downloads[user_id]

# ==================== SAFE METADATA EXTRACTION ====================

async def get_video_metadata_safe(url):
    """Safely extract video metadata with better error handling"""
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, extract_metadata_sync, url)
    except Exception as e:
        print(f"❌ Error getting video metadata: {str(e)}")
        return None

def extract_metadata_sync(url):
    """Synchronous metadata extraction with improved error handling"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'skip_download': True,
            'socket_timeout': 30,
            'retries': 2,
            'no_check_certificate': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
            }
        }
        
        # Add site-specific headers for adult sites
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        if any(adult_site in domain for adult_site in ['pornhub', 'xvideos', 'xnxx', 'xhamster']):
            ydl_opts['http_headers'].update({
                'Referer': f'https://{domain}/',
                'Origin': f'https://{domain}',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
            })
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                return {
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                    'view_count': info.get('view_count', 0),
                    'upload_date': info.get('upload_date', ''),
                    'description': info.get('description', '')[:200] if info.get('description') else '',
                }
    except Exception as e:
        print(f"❌ Metadata extraction failed: {str(e)}")
        return None

# ==================== CONCURRENT DOWNLOAD AND SEND ====================

async def download_and_send_concurrent(client, message, progress_tracker, user_id):
    """Download video and send to user with concurrent support and rate limiting"""
    download_id = progress_tracker.download_id
    url = progress_tracker.url
    status_msg = progress_tracker.status_msg
    
    try:
        download_dir = f"./downloads/{download_id}/"
        os.makedirs(download_dir, exist_ok=True)
        
        def progress_hook(d):
            """Progress hook for yt-dlp with throttling"""
            try:
                current_time = time.time()
                if current_time - progress_tracker.last_update < 2:  # Throttle updates
                    return
                    
                if d['status'] == 'downloading':
                    progress_tracker.downloaded = d.get('downloaded_bytes', 0)
                    progress_tracker.total_size = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
                    progress_tracker.speed = d.get('speed', 0) or 0
                    progress_tracker.eta = d.get('eta', 0) or 0
                    progress_tracker.filename = d.get('filename', 'Unknown')
                    progress_tracker.status = "ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ"
                    progress_tracker.last_update = current_time
                elif d['status'] == 'finished':
                    progress_tracker.status = "ᴄᴏᴍᴘʟᴇᴛᴇᴅ"
                    progress_tracker.filename = d.get('filename', 'Unknown')
            except Exception as e:
                pass
        
        # Configure yt-dlp options with better error handling
        ydl_opts = get_download_options_enhanced(url)
        ydl_opts.update({
            'outtmpl': f'{download_dir}%(title)s.%(ext)s',
            'progress_hooks': [progress_hook],
        })
        
        # Start progress update task
        progress_task = asyncio.create_task(update_progress_concurrent_throttled(progress_tracker))
        
        # Download in a separate thread
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(None, download_video_enhanced, url, ydl_opts)
        
        # Cancel progress updates
        progress_task.cancel()
        
        if not success:
            await status_msg.edit_text(
                "<b>❌ ᴅᴏᴡɴʟᴏᴀᴅ ғᴀɪʟᴇᴅ!</b>\n\n"
                "ᴛʜᴇ ᴠɪᴅᴇᴏ ᴄᴏᴜʟᴅ ɴᴏᴛ ʙᴇ ᴅᴏᴡɴʟᴏᴀᴅᴇᴅ.",
                parse_mode=ParseMode.HTML
            )
            return
        
        await safe_edit_message(status_msg,
            "<b>» ᴅᴏᴡɴʟᴏᴀᴅᴇᴅ!</b>\n\n",
            ParseMode.HTML
        )
        
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
        
        # Process each downloaded file with rate limiting
        uploaded_successfully = False
        total_file_size = 0
        uploaded_files = []

        user_info = {
            'id': message.from_user.id,
            'name': message.from_user.first_name or message.from_user.username or "Gᴇɴɪᴇ"
        }
        
        # Use semaphore to limit concurrent uploads
        async with UPLOAD_SEMAPHORE:
            for file_path in downloaded_files:
                try:
                    file_size = os.path.getsize(file_path)
                    file_name = os.path.basename(file_path)
                    
                    # First upload to user with spoiler (for videos)
                    user_message = await upload_to_user_first_enhanced(client, message, file_path, progress_tracker)
                    
                    if user_message:
                        # Then copy to all dump channels with delay
                        await copy_to_dumps_enhanced(client, user_message, file_name, file_size, user_info)
                        
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
                
                print(f"🔄 Updating stats for user {user_id}: site={site_domain}, size={total_file_size}, type={file_type}")
                success = await update_download_stats(user_id, username, url, total_file_size, file_type)
                if success:
                    print(f"✅ Successfully updated stats for user {user_id}")

            except Exception as e:
                print(f"❌ Error updating stats: {str(e)}")
        
        # Delete the status message after everything is done
        if uploaded_successfully:
            try:
                await status_msg.delete()
                await message.delete()
            except Exception:
                await safe_edit_message(status_msg,
                    "<b>✅ ᴀʟʟ ᴅᴏɴᴇ!</b>",
                    ParseMode.HTML
                )
        else:
            await status_msg.edit_text(
                "<b>❌ ɴᴏ ғɪʟᴇs ᴜᴘʟᴏᴀᴅᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!</b>",
                parse_mode=ParseMode.HTML
            )
        
    except Exception as e:
        await safe_edit_message(status_msg,
            f"<b>❌ ᴇʀʀᴏʀ:</b> {str(e)}",
            ParseMode.HTML
        )
    
    finally:
        cleanup_files(download_dir)
        print(f"✅ Cleaned up directory: {download_dir}")
        # Remove from active downloads
        if user_id in active_downloads:
            active_downloads[user_id] = [t for t in active_downloads[user_id] if t.download_id != download_id]
            if not active_downloads[user_id]:
                del active_downloads[user_id]

# ==================== ENHANCED DOWNLOAD OPTIONS ====================

def get_download_options_enhanced(url):
    """Get enhanced download options with better error handling"""
    from urllib.parse import urlparse
    
    domain = urlparse(url).netloc.lower()
    
    base_opts = {
        'format': 'best[height<=720]/best[height<=480]/best',
        'concurrent_fragment_downloads': 3,
        'retries': 3,
        'fragment_retries': 3,
        'retry_sleep_functions': {
            'http': lambda n: min(2 ** n, 10),
            'fragment': lambda n: min(2 ** n, 5)
        },
        'socket_timeout': 45,
        'http_chunk_size': 1024 * 1024,
        'writesubtitles': False,
        'writeautomaticsub': False,
        'writethumbnail': False,
        'writeinfojson': False,
        'no_check_certificate': True,
        'prefer_insecure': False,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
    }
    
    # Site-specific optimizations
    if 'youtube' in domain or 'youtu.be' in domain:
        base_opts.update({
            'format': 'best[height<=720][protocol^=https]/best[height<=480]/best',
            'extractor_args': {
                'youtube': {
                    'skip': ['dash'],
                    'player_skip': ['js'],
                }
            }
        })
    elif 'instagram' in domain:
        base_opts.update({
            'format': 'best[height<=2160]/best[height<=1080]/best[height<=720]/best',  # Keep 2K support
            'concurrent_fragment_downloads': 2,
            'http_headers': {
                **base_opts['http_headers'],
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
        base_opts.update({
            'format': 'best[height<=720][protocol^=https]/best[height<=480]/best',
            'concurrent_fragment_downloads': 4,
            'http_chunk_size': 2 * 1024 * 1024,
            'socket_timeout': 60,
            'retries': 5,
            'fragment_retries': 5,
            'http_headers': {
                **base_opts['http_headers'],
                'Referer': f'https://{domain}/',
                'Origin': f'https://{domain}',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                'Sec-Fetch-Dest': 'video',
                'Sec-Fetch-Mode': 'no-cors',
                'Sec-Fetch-Site': 'same-origin',
            },
            'hls_prefer_native': True,
            'no_check_certificate': False,
        })
    
    return base_opts


def download_video_enhanced(url, ydl_opts):
    """Enhanced video download with better error handling and fallbacks"""
    try:
        # First attempt with optimized settings
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                return True
        except Exception as e:
            print(f"❌ First download attempt failed: {str(e)}")
            
            # Second attempt with conservative settings
            conservative_opts = {
                **ydl_opts,
                'format': 'best/worst',
                'concurrent_fragment_downloads': 1,
                'socket_timeout': 90,
                'retries': 2,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'
                }
            }
            
            try:
                with yt_dlp.YoutubeDL(conservative_opts) as ydl_conservative:
                    ydl_conservative.download([url])
                    return True
            except Exception as e2:
                print(f"❌ Conservative download attempt failed: {str(e2)}")
                
                # Final attempt with minimal settings
                minimal_opts = {
                    'format': 'worst',
                    'retries': 1,
                    'socket_timeout': 120,
                    'no_check_certificate': True,
                    'http_headers': {
                        'User-Agent': 'curl/7.68.0'
                    }
                }
                minimal_opts.update({k: v for k, v in ydl_opts.items() if k in ['outtmpl', 'progress_hooks']})
                
                try:
                    with yt_dlp.YoutubeDL(minimal_opts) as ydl_minimal:
                        ydl_minimal.download([url])
                        return True
                except Exception as e3:
                    print(f"❌ All download attempts failed. Final error: {str(e3)}")
                    return False
                        
    except Exception as e:
        print(f"❌ Download function error: {str(e)}")
        return False

# ==================== ENHANCED UPLOAD FUNCTIONS ====================

async def upload_to_user_first_enhanced(client, message, file_path, progress_tracker):
    """Enhanced upload to user with better rate limiting"""
    try:
        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        status_msg = progress_tracker.status_msg
        
        # Check if file needs splitting
        if file_size > 1.98 * 1024 * 1024 * 1024:
            await safe_edit_message(status_msg,
                f"<b>📦 sᴘʟɪᴛᴛɪɴɢ ʟᴀʀɢᴇ ғɪʟᴇ</b>\n\n"
                f"<b>📁 ғɪʟᴇ:</b> {file_name}\n"
                f"<b>💾 sɪᴢᴇ:</b> {format_bytes(file_size)}",
                ParseMode.HTML
            )
            
            if is_video_file(file_path):
                from helper_func import split_video
                file_chunks = await split_video(file_path)
            else:
                from helper_func import split_file
                file_chunks = split_file(file_path)
            
            uploaded_messages = []
            
            for i, chunk_path in enumerate(file_chunks, 1):
                chunk_size = os.path.getsize(chunk_path)
                chunk_name = os.path.basename(chunk_path)
                
                await safe_edit_message(status_msg,
                    f"<b>📤 sᴇɴᴅɪɴɢ ᴘᴀʀᴛ {i}/{len(file_chunks)}</b>\n\n"
                    f"<b>📁 ғɪʟᴇ:</b> {chunk_name}\n"
                    f"<b>💾 sɪᴢᴇ:</b> {format_bytes(chunk_size)}",
                    ParseMode.HTML
                )
                
                chunk_msg = await upload_single_file_to_user_enhanced(client, message, chunk_path, progress_tracker, i, len(file_chunks))
                if chunk_msg:
                    uploaded_messages.append(chunk_msg)
                
                try:
                    os.remove(chunk_path)
                except Exception:
                    pass
                
                # Add delay between chunk uploads to prevent rate limiting
                if i < len(file_chunks):
                    await asyncio.sleep(2)
            
            return uploaded_messages[0] if uploaded_messages else None
        else:
            return await upload_single_file_to_user_enhanced(client, message, file_path, progress_tracker)
            
    except Exception as e:
        await safe_edit_message(progress_tracker.status_msg,
            f"<b>❌ ᴜᴘʟᴏᴀᴅ ғᴀɪʟᴇᴅ!</b>\n\n"
            f"<b>📁 ғɪʟᴇ:</b> <code>{os.path.basename(file_path)}</code>\n"
            f"<b>❌ ᴇʀʀᴏʀ:</b> <code>{str(e)}</code>",
            ParseMode.HTML
        )
        return None

async def upload_single_file_to_user_enhanced(client, message, file_path, progress_tracker, part_num=None, total_parts=None):
    """Enhanced single file upload with better rate limiting and error handling"""
    try:
        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        status_msg = progress_tracker.status_msg
        
        # Get user settings
        try:
            settings = await get_file_settings()
            is_premium = await is_premium_user(message.from_user.id)
        except:
            settings = {}
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
        except:
            keyboard = None
        
        # Progress tracking with throttling
        upload_start_time = time.time()
        progress_data = {
            'current': 0,
            'total': file_size,
            'start_time': upload_start_time,
            'last_update': 0
        }
        
        def upload_progress(current, total):
            current_time = time.time()
            if current_time - progress_data['last_update'] >= 3:  # Update every 3 seconds
                progress_data['current'] = current
                progress_data['total'] = total
                progress_data['last_update'] = current_time
        
        # Start progress update task
        progress_task = asyncio.create_task(update_upload_progress_enhanced(status_msg, progress_data, file_name, part_num, total_parts))
        
        # Generate thumbnail for videos
        thumbnail_path = None
        if file_path.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm')):
            thumbnail_path = f"{os.path.dirname(file_path)}/thumb_{int(time.time())}.jpg"
            try:
                generated_thumb = await generate_thumbnail(file_path, thumbnail_path, 10)
                if not generated_thumb:
                    thumbnail_path = None
            except:
                thumbnail_path = None
        
        # Get video dimensions
        width, height = 1280, 720
        if file_path.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm')):
            try:
                width, height = await get_video_dimensions(file_path)
            except:
                pass
        
        user_message = None
        metadata = progress_tracker.metadata
        
        try:
            # Add retry logic for uploads
            max_retries = 3
            for attempt in range(max_retries):
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
                            has_spoiler=spoiler_enabled
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
                    break  # Success, exit retry loop
                    
                except FloodWait as e:
                    print(f"⚠️ FloodWait: Waiting {e.value} seconds...")
                    await asyncio.sleep(e.value)
                    if attempt == max_retries - 1:
                        raise
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    print(f"⚠️ Upload attempt {attempt + 1} failed: {str(e)}")
                    await asyncio.sleep(5)  # Wait before retry
        
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
        await safe_edit_message(status_msg,
            f"<b>❌ ᴜᴘʟᴏᴀᴅ ғᴀɪʟᴇᴅ!</b>\n\n"
            f"<b>📁 ғɪʟᴇ:</b> <code>{file_name}</code>\n"
            f"<b>❌ ᴇʀʀᴏʀ:</b> <code>{str(e)}</code>",
            ParseMode.HTML
        )
        return None

# ==================== ENHANCED COPY TO DUMPS ====================

async def copy_to_dumps_enhanced(client, user_message, file_name, file_size, user_info):
    """Enhanced copy to dumps with rate limiting and error handling"""
    try:
        # Create dump caption without inline keyboard
        dump_caption = f"<b>{file_name}</b> | <b>{format_bytes(file_size)}</b>\n<b>ʟᴇᴇᴄʜᴇᴅ ʙʏ :</b> <a href='tg://user?id={user_info['id']}'>{user_info['name']}</a>"
        
        for i, dump_id in enumerate(DUMP_CHAT_IDS):
            try:
                # Add delay between dump uploads to prevent rate limiting
                if i > 0:
                    await asyncio.sleep(3)
                
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
                
            except FloodWait as e:
                print(f"⚠️ FloodWait for dump {dump_id}: Waiting {e.value} seconds...")
                await asyncio.sleep(e.value)
                # Retry once after FloodWait
                try:
                    await client.copy_message(
                        chat_id=dump_id,
                        from_chat_id=user_message.chat.id,
                        message_id=user_message.id,
                        caption=dump_caption,
                        parse_mode=ParseMode.HTML
                    )
                except Exception:
                    pass
            except Exception as e:
                print(f"❌ Failed to copy to dump {dump_id}: {str(e)}")
                continue  # Continue with other dump channels
                
    except Exception as e:
        print(f"❌ Error in copy_to_dumps_enhanced: {str(e)}")

# ==================== ENHANCED PROGRESS UPDATE FUNCTIONS ====================

async def update_progress_concurrent_throttled(progress_tracker):
    """Throttled progress update to prevent message edit spam"""
    try:
        status_msg = progress_tracker.status_msg
        last_edit_time = 0
        
        while progress_tracker.status != "ᴄᴏᴍᴘʟᴇᴛᴇᴅ":
            current_time = time.time()
            
            # Only update every 5 seconds to prevent rate limiting
            if current_time - last_edit_time < 5:
                await asyncio.sleep(1)
                continue
            
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
            
            success = await safe_edit_message(status_msg, progress_text, ParseMode.HTML)
            if success:
                last_edit_time = current_time
            
            await asyncio.sleep(2)
            
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"❌ Progress update error: {str(e)}")

async def update_upload_progress_enhanced(status_msg, progress_data, file_name, part_num=None, total_parts=None):
    """Enhanced upload progress with better throttling"""
    try:
        last_edit_time = 0
        
        while progress_data['current'] < progress_data['total']:
            current_time = time.time()
            current = progress_data['current']
            total = progress_data['total']
            
            if current == 0:
                await asyncio.sleep(2)
                continue
            
            # Only update every 4 seconds to prevent rate limiting
            if current_time - last_edit_time < 4:
                await asyncio.sleep(1)
                continue
            
            total_time = current_time - progress_data['start_time']
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
            
            success = await safe_edit_message(status_msg, status_text, ParseMode.HTML)
            if success:
                last_edit_time = current_time
            
            await asyncio.sleep(1)
            
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"❌ Upload progress error: {str(e)}")

# ==================== SAFE MESSAGE EDIT FUNCTION ====================

async def safe_edit_message(message, text, parse_mode=None, max_retries=3):
    """Safely edit message with retry logic and rate limiting"""
    for attempt in range(max_retries):
        try:
            await message.edit_text(text, parse_mode=parse_mode)
            return True
        except FloodWait as e:
            if attempt < max_retries - 1:
                print(f"⚠️ FloodWait during message edit: Waiting {e.value} seconds...")
                await asyncio.sleep(e.value)
            else:
                print(f"❌ FloodWait exceeded max retries for message edit")
                return False
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
            else:
                print(f"❌ Failed to edit message after {max_retries} attempts: {str(e)}")
                return False
    return False

# ==================== RATE LIMITING SEMAPHORE ====================

UPLOAD_SEMAPHORE = asyncio.Semaphore(3)  # Limit concurrent uploads

# ==================== ENHANCED UTILITY FUNCTIONS ====================

def create_progress_bar(percentage, length=20):
    """Create a visual progress bar"""
    filled = int(length * percentage / 100)
    bar = "█" * filled + "░" * (length - filled)
    return bar

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
        return "0s"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"

def extract_domain(url):
    """Extract domain from URL"""
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.lower()
    except:
        return "unknown"

def cleanup_files(directory):
    """Clean up downloaded files and directory"""
    try:
        if os.path.exists(directory):
            import shutil
            shutil.rmtree(directory)
            print(f"✅ Cleaned up directory: {directory}")
    except Exception as e:
        print(f"❌ Error cleaning up {directory}: {str(e)}")

# ==================== ENHANCED METADATA FUNCTIONS ====================

async def get_video_metadata(url):
    """Get video metadata without downloading"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'skip_download': True,
            'writeinfojson': False,
            'socket_timeout': 30,
        }
        
        loop = asyncio.get_event_loop()
        
        def extract_info():
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)
            except Exception:
                return None
        
        info = await loop.run_in_executor(None, extract_info)
        
        if info:
            return {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'upload_date': info.get('upload_date', ''),
                'description': info.get('description', '')[:200] + '...' if info.get('description') else '',
            }
    except Exception as e:
        print(f"❌ Error extracting metadata: {str(e)}")
    
    return None

async def generate_thumbnail(video_path, thumb_path, time_offset=10):
    """Generate thumbnail from video"""
    try:
        import subprocess
        
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-ss', str(time_offset),
            '-vframes', '1',
            '-vf', 'scale=320:240',
            '-y',
            thumb_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        await process.communicate()
        
        return os.path.exists(thumb_path)
    except Exception:
        return False

async def get_video_dimensions(video_path):
    """Get video dimensions"""
    try:
        import subprocess
        
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams',
            video_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, _ = await process.communicate()
        
        if stdout:
            import json
            data = json.loads(stdout.decode())
            
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    width = stream.get('width', 1280)
                    height = stream.get('height', 720)
                    return width, height
    except Exception:
        pass
    
    return 1280, 720

# ==================== ENHANCED SETTINGS FUNCTIONS ====================

async def get_file_settings():
    """Get file upload settings"""
    try:
        # Default settings
        return {
            'protect_content': False,
            'show_caption': True,
            'auto_delete': False,
            'auto_delete_time': 300,
            'inline_buttons': True,
            'spoiler_enabled': False,
        }
    except Exception:
        return {}

async def is_premium_user(user_id):
    """Check if user is premium"""
    try:
        from config import Config
        return user_id in Config.ADMINS
    except Exception:
        return False

async def create_user_keyboard(is_premium=False):
    """Create inline keyboard for user uploads"""
    try:
        from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        buttons = []
        return InlineKeyboardMarkup(buttons)
    except Exception:
        return None

# ==================== REPLACE ORIGINAL FUNCTIONS ====================

# Replace the original functions with enhanced versions
update_progress_concurrent = update_progress_concurrent_throttled
get_download_options = get_download_options_enhanced
download_video = download_video_enhanced
copy_to_dumps = copy_to_dumps_enhanced
upload_to_user_first = upload_to_user_first_enhanced
upload_single_file_to_user = upload_single_file_to_user_enhanced
update_upload_progress = update_upload_progress_enhanced

print("✅ Enhanced download module with rate limiting and error handling loaded successfully")
