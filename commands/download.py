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

# Global variables to track downloads
active_downloads = {}

# Stats file path
STATS_FILE = "bot_stats.json"

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

def load_stats():
    """Load stats from file"""
    try:
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, 'r') as f:
                return json.load(f)
        return {
            "total_downloads": 0,
            "users": {},
            "sites": {},
            "daily_stats": {},
            "file_types": {}
        }
    except Exception as e:
        logging.error(f"Error loading stats: {e}")
        return {
            "total_downloads": 0,
            "users": {},
            "sites": {},
            "daily_stats": {},
            "file_types": {}
        }

def save_stats(stats):
    """Save stats to file"""
    try:
        with open(STATS_FILE, 'w') as f:
            json.dump(stats, f, indent=2)
    except Exception as e:
        logging.error(f"Error saving stats: {e}")

def format_bytes(bytes_value):
    """Convert bytes to human readable format"""
    if bytes_value == 0:
        return "0 ʙ"
    
    units = ['ʙ', 'ᴋʙ', 'ᴍʙ', 'ɢʙ', 'ᴛʙ']
    unit_index = 0
    
    while bytes_value >= 1024 and unit_index < len(units) - 1:
        bytes_value /= 1024
        unit_index += 1
    
    return f"{bytes_value:.1f} {units[unit_index]}"

def format_time(seconds):
    """Convert seconds to human readable time format"""
    if seconds <= 0:
        return "0s"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}ʜ {minutes}ᴍ {secs}s"
    elif minutes > 0:
        return f"{minutes}ᴍ {secs}s"
    else:
        return f"{secs}s"

def format_duration(seconds):
    """Format duration from seconds to HH:MM:SS or MM:SS"""
    if not seconds or seconds <= 0:
        return "00:00"
    
    try:
        seconds = int(float(seconds))
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"
    except:
        return "00:00"

def create_progress_bar(percentage):
    """Create a visual progress bar"""
    filled = int(percentage / 10)
    empty = 10 - filled
    return "█" * filled + "░" * empty

async def get_video_dimensions(video_path):
    """Get video width and height using ffprobe"""
    try:
        process = await asyncio.create_subprocess_exec(
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height', '-of', 'csv=s=x:p=0', video_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logging.warning(f"ffprobe error: {stderr.decode()}")
            return 1280, 720
        
        output = stdout.decode().strip()
        if 'x' in output:
            width, height = map(int, output.split('x'))
            if width > 0 and height > 0:
                return width, height
        
        return 1280, 720
        
    except Exception as e:
        logging.warning(f"Error getting video dimensions: {e}")
        return 1280, 720

async def get_video_metadata(url):
    """Extract video metadata using yt-dlp"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'skip_download': True,
        }
        
        loop = asyncio.get_event_loop()
        metadata = await loop.run_in_executor(None, extract_metadata, url, ydl_opts)
        
        if metadata:
            return {
                'title': metadata.get('title', 'Unknown'),
                'duration': metadata.get('duration', 0),
                'duration_string': format_duration(metadata.get('duration', 0)),
                'uploader': metadata.get('uploader', 'Unknown'),
                'view_count': metadata.get('view_count', 0),
                'filesize': metadata.get('filesize', 0),
                'resolution': metadata.get('resolution', 'Unknown'),
            }
        return None
        
    except Exception as e:
        print(f"❌ Metadata extraction error: {e}")
        return None

def extract_metadata(url, ydl_opts):
    """Extract metadata in thread"""
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info
    except Exception as e:
        print(f"❌ Extract metadata error: {e}")
        return None

async def generate_thumbnail(video_path: str, output_path: str, time_position: int = 10) -> str:
    """Generate high-quality thumbnail with database-stored watermark settings"""
    try:
        # Get watermark settings from database
        watermark_settings = await get_watermark_settings()
        
        if watermark_settings.get('enabled', False):
            text = watermark_settings.get('text', Config.BOT_NAME).replace("'", "\\'")
            position = watermark_settings.get('position', 'bottom-right')
            size = watermark_settings.get('font_size', 32)
            color = watermark_settings.get('color', 'white')
            shadow_color = watermark_settings.get('shadow_color', 'black')
            box_color = watermark_settings.get('box_color', 'black@0.0')
            
            # Position mapping
            pos_map = {
                'top-left': 'x=15:y=15',
                'top-right': 'x=w-tw-15:y=15',
                'bottom-left': 'x=15:y=h-th-15',
                'bottom-right': 'x=w-tw-15:y=h-th-15',
                'center': 'x=(w-tw)/2:y=(h-th)/2',
                'top-center': 'x=(w-tw)/2:y=15',
                'bottom-center': 'x=(w-tw)/2:y=h-th-15'
            }
            pos = pos_map.get(position, 'x=w-tw-15:y=h-th-15')
            
            # Dynamic font size based on video resolution
            dynamic_size = max(16, size)
            
            # Create watermark filter based on box settings
            if box_color.endswith("@0.0") or box_color == "none":
                # No background box, use shadow and border
                watermark_filter = (
                    f"scale=480:-1,"
                    f"drawtext=text='{text}':"
                    f"fontcolor={color}:"
                    f"fontsize={dynamic_size}:"
                    f"{pos}:"
                    f"shadowcolor={shadow_color}:"
                    f"shadowx=3:shadowy=3:"
                    f"borderw=2:"
                    f"bordercolor={shadow_color}"
                )
            else:
                # With background box
                watermark_filter = (
                    f"scale=480:-1,"
                    f"drawtext=text='{text}':"
                    f"fontcolor={color}:"
                    f"fontsize={dynamic_size}:"
                    f"box=1:"
                    f"boxcolor={box_color}:"
                    f"boxborderw=5:"
                    f"{pos}"
                )
        else:
            # No watermark, just scale
            watermark_filter = "scale=480:-1"
        
        # Generate thumbnail using ffmpeg
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "panic",
            "-ss", str(time_position),
            "-i", video_path,
            "-vframes", "1",
            "-vf", watermark_filter,
            "-q:v", "1",
            "-pix_fmt", "yuv420p",
            "-compression_level", "0",
            output_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        
        try:
            await asyncio.wait_for(process.communicate(), timeout=15)
            
            if process.returncode == 0 and os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                if file_size > 1024:  # At least 1KB
                    return output_path
                else:
                    return None
            else:
                return None
                
        except asyncio.TimeoutError:
            process.kill()
            return None
            
    except Exception as e:
        print(f"❌ Thumbnail generation failed: {e}")
        return None

# Add this function to check admin
def check_admin(_, __, message):
    """Check if user is admin"""
    return Config.is_admin(message.from_user.id)

@Client.on_message(filters.private & ~filters.command([
    "start", "help", "stats", "mystats", "leaderboard", "history", "cancel",
    "fix_dumps", "check_dumps", "force_meet", "reset_stats", "broadcast", 
    "watermark", "logs", "cleanup", "restart", "test"
]))
async def handle_url_message(client: Client, message: Message):
    """Handle URL messages for download"""
    try:
        if not await check_subscription(client, message):
            return
        
        if not message.text:
            return
            
        url = message.text.strip()
        
        # Basic URL validation
        if not re.match(r'https?://', url):
            await message.reply_text(
                "<b>❌ ɪɴᴠᴀʟɪᴅ ᴜʀʟ</b>\n\n"
                "ᴘʟᴇᴀsᴇ sᴇɴᴅ ᴀ ᴠᴀʟɪᴅ ᴜʀʟ sᴛᴀʀᴛɪɴɢ ᴡɪᴛʜ http:// ᴏʀ https://",
                parse_mode=ParseMode.HTML
            )
            return
        
        user_id = message.from_user.id
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
        
        # Continue with existing download logic...
        active_downloads[user_id] = ProgressTracker()
        
        status_msg = await message.reply_text(
            "<b>📥 sᴛᴀʀᴛɪɴɢ ᴅᴏᴡɴʟᴏᴀᴅ</b>\n\n"
            f"<b>🔗 ᴜʀʟ:</b> <code>{url}</code>\n\n"
            f"<b>⏳ sᴛᴀᴛᴜs:</b> ᴘʀᴇᴘᴀʀɪɴɢ...",
            parse_mode=ParseMode.HTML
        )
        
        # Extract metadata and start download
        metadata = await get_video_metadata(url)
        if metadata:
            active_downloads[user_id].metadata = metadata
        
        await download_and_send(client, message, status_msg, url, user_id)
        
    except Exception as e:
        print(f"❌ Error in handle_url_message: {e}")
        await message.reply_text(
            f"<b>❌ ᴇʀʀᴏʀ</b>\n\n<code>{str(e)}</code>",
            parse_mode=ParseMode.HTML
        )
        if message.from_user.id in active_downloads:
            del active_downloads[message.from_user.id]

async def download_and_send(client, message, status_msg, url, user_id):
    """Download video and send to user with progress tracking"""
    try:
        # Create download directory
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
        ydl_opts = {
            'outtmpl': f'{download_dir}%(title)s.%(ext)s',
            'format': 'best[filesize<2G]/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'progress_hooks': [progress_hook],
        }
        
        # Start progress update task for downloading
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
        
        # STEP 2: Show download complete message
        await status_msg.edit_text(
            "<b>✅ ᴅᴏᴡɴʟᴏᴀᴅ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!</b>\n\n"
            "<b>📋 ᴘʀᴇᴘᴀʀɪɴɢ ғɪʟᴇs ғᴏʀ ᴜᴘʟᴏᴀᴅ...</b>",
            parse_mode=ParseMode.HTML
        )
        
        # Small delay to show the message
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
                
                # STEP 3: Start uploading (upload_to_dump will handle progress)
                print(f"📤 Starting upload: {file_name} ({format_bytes(file_size)})")
                
                # Upload to first dump channel (this will show live progress)
                dump_message = await upload_to_dump(client, file_path, DUMP_CHAT_IDS[0], progress_tracker, status_msg)
                
                if dump_message:
                    # STEP 4: Show upload complete message briefly
                    await status_msg.edit_text(
                        f"<b>✅ ᴜᴘʟᴏᴀᴅ sᴜᴄᴄᴇssғᴜʟ!</b>\n\n"
                        f"<b>📁 ғɪʟᴇ:</b> <code>{file_name}</code>\n"
                        f"<b>💾 sɪᴢᴇ:</b> {format_bytes(file_size)}\n"
                        f"<b>📤 ᴄᴏᴘʏɪɴɢ ᴛᴏ ᴏᴛʜᴇʀ ᴄʜᴀɴɴᴇʟs...</b>",
                        parse_mode=ParseMode.HTML
                    )
                    
                    # Copy to other dump channels (without buttons)
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
                        f"<b>📁 ғɪʟᴇ:</b> <code>{file_name}</code>",
                        parse_mode=ParseMode.HTML
                    )
                    
                    # Create inline keyboard ONLY for user messages
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
                            reply_markup=user_keyboard  # Only for user messages
                        )
                    except Exception as e:
                        print(f"❌ Error sending to user: {e}")
                        # Fallback: send without keyboard
                        await client.copy_message(
                            chat_id=message.chat.id,
                            from_chat_id=DUMP_CHAT_IDS[0],
                            message_id=dump_message.id
                        )
                    
                    # Track successful upload
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
                # Extract site domain from URL
                site_domain = extract_domain(url)
                
                # Get user info
                username = message.from_user.first_name or message.from_user.username or "Unknown"
                
                # Determine file type
                file_ext = os.path.splitext(uploaded_files[0]['name'])[1].lower()
                if file_ext in ['.mp4', '.mkv', '.avi', '.mov', '.webm']:
                    file_type = 'video'
                elif file_ext in ['.mp3', '.m4a', '.wav', '.flac', '.ogg']:
                    file_type = 'audio'
                else:
                    file_type = 'document'
                
                # Update download statistics in database
                success = await update_download_stats(user_id, username, url, file_size, file_type)

                if success:
                    print(f"✅ Stats updated successfully for user {user_id}")
                else:
                    print(f"❌ Failed to update stats for user {user_id}")

            except Exception as e:
                print(f"❌ Error updating download stats: {e}")
        
        # STEP 5: Delete the status message after everything is done
        if uploaded_successfully:
            try:
                await asyncio.sleep(2)  # Brief delay to show final message
                await status_msg.delete()
            except Exception:
                # If can't delete, just edit to final message
                await status_msg.edit_text(
                    "<b>✅ ᴀʟʟ ᴅᴏɴᴇ!</b>",
                    parse_mode=ParseMode.HTML
                )
        else:
            # If no files uploaded successfully, show error
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
        # Cleanup
        cleanup_files(f"./downloads/{user_id}/")
        if user_id in active_downloads:
            del active_downloads[user_id]

def extract_domain(url: str) -> str:
    """Extract domain from URL"""
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        # Remove www. prefix and return clean domain
        clean_domain = domain.replace('www.', '') if domain.startswith('www.') else domain
        return clean_domain.lower()
    except Exception as e:
        print(f"Error extracting domain from {url}: {e}")
        return "unknown"

def format_bytes(bytes_value):
    """Format bytes to human readable format"""
    if bytes_value == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    import math
    i = int(math.floor(math.log(bytes_value, 1024)))
    p = math.pow(1024, i)
    s = round(bytes_value / p, 2)
    return f"{s} {size_names[i]}"


async def upload_to_dump(client, file_path, dump_id, progress_tracker, status_msg):
    """Upload file to dump channel with progress using user session if available"""
    try:
        # Use user client if available, otherwise use bot client
        upload_client = user_client if user_client else client
        
        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        
        # Check if file needs splitting
        if file_size > 1.98 * 1024 * 1024 * 1024:  # 1.98GB
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
                
                # Upload chunk
                chunk_msg = await upload_single_file(upload_client, chunk_path, dump_id, progress_tracker, status_msg, i, len(file_chunks))
                if chunk_msg:
                    uploaded_messages.append(chunk_msg)
                
                # Clean up chunk file
                try:
                    os.remove(chunk_path)
                except:
                    pass
            
            return uploaded_messages[0] if uploaded_messages else None
        else:
            # Show initial upload message for single files
            # await status_msg.edit_text(
            #     f"<b>📤 ᴜᴘʟᴏᴀᴅɪɴɢ </b>\n\n"
            #     f"<b>📁 ғɪʟᴇ:</b> <code>{file_name}</code>\n"
            #     f"<b>💾 sɪᴢᴇ:</b> {format_bytes(file_size)}\n"
            #     f"<b>📊 ᴘʀᴏɢʀᴇss:</b> 0.0%\n"
            #     f"<b>⚡ sᴘᴇᴇᴅ:</b> ᴄᴀʟᴄᴜʟᴀᴛɪɴɢ...\n"
            #     f"<b>⏳ sᴛᴀᴛᴜs:</b> sᴛᴀʀᴛɪɴɢ ᴜᴘʟᴏᴀᴅ...",
            #     parse_mode=ParseMode.HTML
            # )
            
            # Upload single file (NO KEYBOARD - dump channel only)
            return await upload_single_file(upload_client, file_path, dump_id, progress_tracker, status_msg)
        
    except Exception as e:
        print(f"❌ Error uploading to dump: {e}")
        await status_msg.edit_text(
            f"<b>❌ ᴜᴘʟᴏᴀᴅ ғᴀɪʟᴇᴅ!</b>\n\n"
            f"<b>📁 ғɪʟᴇ:</b> <code>{os.path.basename(file_path)}</code>\n"
            f"<b>❌ ᴇʀʀᴏʀ:</b> <code>{str(e)}</code>",
            parse_mode=ParseMode.HTML
        )
        return None


async def upload_single_file(upload_client, file_path, dump_id, progress_tracker, status_msg, part_num=None, total_parts=None):
    """Upload a single file with real-time progress tracking and speed display"""
    try:
        import time
        
        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        
        # Initialize progress tracking variables
        last_update = 0
        upload_start_time = time.time()
        last_uploaded = 0
        
        # Show initial upload message
        initial_text = f"<b>📤 ᴜᴘʟᴏᴀᴅɪɴɢ</b>\n\n"
        if part_num and total_parts:
            initial_text = f"<b>📤 ᴜᴘʟᴏᴀᴅɪɴɢ ᴘᴀʀᴛ {part_num}/{total_parts}</b>\n\n"
        
        initial_text += (
            f"<b>📁 ғɪʟᴇ:</b> <code>{file_name}</code>\n"
            f"<b>💾 sɪᴢᴇ:</b> {format_bytes(file_size)}\n"
            f"<b>📊 ᴘʀᴏɢʀᴇss:</b> 0.0%\n"
            f"<b>⚡ sᴘᴇᴇᴅ:</b> ᴄᴀʟᴄᴜʟᴀᴛɪɴɢ...\n"
            f"<b>⏳ sᴛᴀᴛᴜs:</b> sᴛᴀʀᴛɪɴɢ ᴜᴘʟᴏᴀᴅ..."
        )
        
        await status_msg.edit_text(initial_text, parse_mode=ParseMode.HTML)
        
        # Create a separate task for progress updates
        progress_data = {
            'current': 0,
            'total': file_size,
            'last_update': 0,
            'start_time': upload_start_time,
            'last_uploaded': 0
        }
        
        # Progress update task that runs independently
        async def update_progress_task():
            while progress_data['current'] < progress_data['total']:
                try:
                    current = progress_data['current']
                    total = progress_data['total']
                    
                    if current == 0:
                        await asyncio.sleep(1)
                        continue
                    
                    # Calculate speeds and ETA
                    now = time.time()
                    total_time = now - progress_data['start_time']
                    avg_speed = current / total_time if total_time > 0 else 0
                    
                    remaining_bytes = total - current
                    eta = remaining_bytes / avg_speed if avg_speed > 0 else 0
                    
                    # Calculate percentage and create progress bar
                    percentage = (current / total) * 100 if total > 0 else 0
                    progress_bar = create_progress_bar(percentage)
                    
                    # Create status text
                    if part_num and total_parts:
                        status_text = f"<b>📤 ᴜᴘʟᴏᴀᴅɪɴɢ ᴘᴀʀᴛ {part_num}/{total_parts}</b>\n\n"
                    else:
                        status_text = f"<b>📤 ᴜᴘʟᴏᴀᴅɪɴɢ..</b>\n\n"
                    
                    status_text += (
                        f"<b>📁 ғɪʟᴇ:</b> <code>{file_name}</code>\n"
                        f"<b>💾 sɪᴢᴇ:</b> {format_bytes(file_size)}\n\n"
                        f"<b>📊 ᴘʀᴏɢʀᴇss:</b>\n"
                        f"<code>{progress_bar}</code> <b>{percentage:.1f}%</b>\n\n"
                        f"<b>📤 ᴜᴘʟᴏᴀᴅᴇᴅ:</b> {format_bytes(current)} / {format_bytes(total)}\n"
                        f"<b>📈 ᴀᴠᴇʀᴀɢᴇ sᴘᴇᴇᴅ:</b> {format_bytes(avg_speed)}/s\n"
                        f"<b>⏱️ ᴇᴛᴀ:</b> {format_time(eta)}"
                    )
                    
                    # Update message
                    await safe_edit_message(status_msg, status_text)
                    await asyncio.sleep(2)  # Update every 2 seconds
                    
                except Exception as e:
                    print(f"Progress update error: {e}")
                    await asyncio.sleep(2)
        
        # Simple progress callback that just updates the data
        def upload_progress(current, total):
            progress_data['current'] = current
            progress_data['total'] = total
        
        # Start progress update task
        progress_task = asyncio.create_task(update_progress_task())
        
        # Create caption with metadata - NO INLINE KEYBOARD for dump channels
        metadata = progress_tracker.metadata
        if part_num and total_parts:
            caption = f"<b>📁 {file_name}</b>\n<b>📦 Part {part_num}/{total_parts} | {format_bytes(file_size)}</b>\n\n"
        else:
            caption = f"<b>📁 {file_name}</b>\n<b>📦 {format_bytes(file_size)}</b>\n\n"
        
        # Add metadata if available
        # if metadata:
        #     if metadata.get('title'):
        #         caption += f"<b>🎬 ᴛɪᴛʟᴇ:</b> {metadata['title'][:50]}{'...' if len(metadata['title']) > 50 else ''}\n"
        #     if metadata.get('duration'):
        #         caption += f"<b>⏱️ ᴅᴜʀᴀᴛɪᴏɴ:</b> {metadata['duration_string']}\n"
        #     if metadata.get('uploader'):
        #         caption += f"<b>👤 ᴜᴘʟᴏᴀᴅᴇʀ:</b> {metadata['uploader'][:30]}{'...' if len(metadata['uploader']) > 30 else ''}\n"
        #     caption += "\n"
        
        # caption += f"<b>🤖 ᴜᴘʟᴏᴀᴅᴇᴅ ʙʏ:</b> @{Config.BOT_USERNAME}"
        
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
        max_retries = 3
        dump_message = None
        
        try:
            if file_path.lower().endswith(('.mp4', '.mkv', '.avi', '.mov', '.webm')):
                # Send as video to DUMP CHANNEL - NO KEYBOARD
                dump_message = await upload_client.send_video(
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
                dump_message = await upload_client.send_audio(
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
                dump_message = await upload_client.send_document(
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


async def safe_edit_message(message, text):
    """Safely edit message without throwing exceptions"""
    try:
        await message.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception:
        # Silently ignore all edit errors (rate limits, message not modified, etc.)
        pass

def cleanup_files(directory):
    """Clean up downloaded files"""
    try:
        if os.path.exists(directory):
            for file in os.listdir(directory):
                file_path = os.path.join(directory, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
            os.rmdir(directory)
            print(f"✅ Cleaned up: {directory}")
    except Exception as e:
        print(f"❌ Cleanup error: {e}")


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
            
            try:
                await status_msg.edit_text(progress_text, parse_mode=ParseMode.HTML)
            except Exception:
                # Ignore edit errors
                pass
            
            await asyncio.sleep(3)  # Update every 3 seconds
            
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"❌ Progress update error: {e}")

def download_video(url, ydl_opts):
    """Download video using yt-dlp with speed optimizations"""
    try:
        import yt_dlp
        import os
        import platform
        from urllib.parse import urlparse
        
        domain = urlparse(url).netloc.lower()
        
        # Speed-optimized options
        speed_opts = {
            **ydl_opts,
            
            # Connection optimization
            'concurrent_fragment_downloads': 4,  # Download 4 fragments simultaneously
            'retries': 5,
            'fragment_retries': 5,
            'retry_sleep_functions': {
                'http': lambda n: min(2 ** n, 10),  # Faster retry intervals
                'fragment': lambda n: min(2 ** n, 5)
            },
            
            # Buffer and timeout settings
            'socket_timeout': 30,
            'http_chunk_size': 1024 * 1024,  # 1MB chunks
            
            # Headers for better speed
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            },
            
            # Disable unnecessary features for speed
            'writesubtitles': False,
            'writeautomaticsub': False,
            'writethumbnail': False,
            'writeinfojson': False,
            'no_check_certificate': True,
            'prefer_insecure': True,  # Use HTTP when possible for speed
        }
        
        # Site-specific speed optimizations
        if 'youtube' in domain or 'youtu.be' in domain:
            speed_opts.update({
                'format': 'best[height<=720][protocol^=https]/best[height<=480]/best',
                'extractor_args': {
                    'youtube': {
                        'skip': ['dash'],  # Skip DASH for faster downloads
                        'player_skip': ['js'],
                    }
                }
            })
            
        elif 'instagram' in domain:
            speed_opts.update({
                'format': 'best/worst',
                'concurrent_fragment_downloads': 2,  # Instagram is more restrictive
            })
            
        elif any(adult_site in domain for adult_site in ['pornhub', 'xvideos', 'xnxx', 'xhamster']):
            speed_opts.update({
                'format': 'best[height<=720]/best',
                'concurrent_fragment_downloads': 6,  # Adult sites often allow more connections
                'http_headers': {
                    **speed_opts['http_headers'],
                    'Referer': f'https://{domain}/',
                }
            })
            
        else:
            # Generic sites
            speed_opts.update({
                'format': 'best/worst',
                'concurrent_fragment_downloads': 3,
            })
        
        print(f"🚀 Starting optimized download from {domain}...")
        print(f"   Concurrent fragments: {speed_opts.get('concurrent_fragment_downloads', 1)}")
        print(f"   Chunk size: {speed_opts.get('http_chunk_size', 'default')}")
        
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


def cleanup_files(directory):
    """Clean up downloaded files"""
    try:
        if os.path.exists(directory):
            for file in os.listdir(directory):
                file_path = os.path.join(directory, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
            os.rmdir(directory)
            print(f"✅ Cleaned up: {directory}")
    except Exception as e:
        print(f"❌ Cleanup error: {e}")

@Client.on_message(filters.command("cancel") & filters.private)
async def cancel_command(client: Client, message: Message):
    """Cancel active download"""
    try:
        user_id = message.from_user.id
        
        if user_id in active_downloads:
            del active_downloads[user_id]
            cleanup_files(f"./downloads/{user_id}/")
            await message.reply_text(
                "<b>✅ ᴅᴏᴡɴʟᴏᴀᴅ ᴄᴀɴᴄᴇʟʟᴇᴅ!</b>",
                parse_mode=ParseMode.HTML
            )
        else:
            await message.reply_text(
                "<b>❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅs</b>\n\n"
                "ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴀɴʏ ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅs ᴛᴏ ᴄᴀɴᴄᴇʟ.",
                parse_mode=ParseMode.HTML
            )
            
    except Exception as e:
        print(f"❌ Error in cancel command: {e}")
        await message.reply_text(
            "<b>❌ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ ᴡʜɪʟᴇ ᴄᴀɴᴄᴇʟʟɪɴɢ</b>",
            parse_mode=ParseMode.HTML
        )

@Client.on_message(filters.command("stats") & filters.private)
async def stats_command(client: Client, message: Message):
    """Handle /stats command with database integration"""

    if user_id not in [7560922302]:  # Replace with your admin ID
        await message.reply_text("❌ <b>ᴀᴅᴍɪɴ ᴏɴʟʏ ᴄᴏᴍᴍᴀɴᴅ!</b>", parse_mode=ParseMode.HTML)
        return
    
    try:
        
        # Get stats from database
        stats = await get_stats()
        user_count = await get_user_count()
        
        # Get additional stats
        total_downloads = stats.get('total_downloads', 0)
        total_file_size = stats.get('total_file_size', 0)
        
        # Format file size
        def format_size(size_bytes):
            if size_bytes == 0:
                return "0 B"
            size_names = ["B", "KB", "MB", "GB", "TB"]
            import math
            i = int(math.floor(math.log(size_bytes, 1024)))
            p = math.pow(1024, i)
            s = round(size_bytes / p, 2)
            return f"{s} {size_names[i]}"
        
        stats_text = (
            "<b>📊 ʙᴏᴛ sᴛᴀᴛɪsᴛɪᴄs</b>\n\n"
            f"<b>🤖 ʙᴏᴛ ɴᴀᴍᴇ:</b> {Config.BOT_NAME}\n"
            f"<b>👥 ᴛᴏᴛᴀʟ ᴜsᴇʀs:</b> {user_count:,}\n"
            f"<b>📥 ᴛᴏᴛᴀʟ ᴅᴏᴡɴʟᴏᴀᴅs:</b> {total_downloads:,}\n"
            f"<b>💾 ᴛᴏᴛᴀʟ ғɪʟᴇ sɪᴢᴇ:</b> {format_size(total_file_size)}\n"
            f"<b>🔄 ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅs:</b> {len(active_downloads)}\n"
            f"<b>📏 ᴍᴀx ғɪʟᴇ sɪᴢᴇ:</b> 2ɢʙ\n\n"
        )
        
        # Show top sites if available
        sites = stats.get('sites', {})
        if sites:
            top_sites = sorted(sites.items(), key=lambda x: x[1], reverse=True)[:5]
            stats_text += "<b>🌐 ᴛᴏᴘ sɪᴛᴇs:</b>\n"
            for site, count in top_sites:
                stats_text += f"• {site}: {count:,} downloads\n"
            stats_text += "\n"
        
        # Show top users if available
        top_users_data = stats.get('top_users', {})
        if top_users_data:
            sorted_users = sorted(top_users_data.items(), key=lambda x: x[1], reverse=True)[:5]
            stats_text += "<b>👑 ᴛᴏᴘ ᴜsᴇʀs:</b>\n"
            for user_id, download_count in sorted_users:
                try:
                    user = await client.get_users(int(user_id))
                    name = user.first_name or "Unknown"
                    stats_text += f"• {name}: {download_count:,} downloads\n"
                except:
                    stats_text += f"• User {user_id}: {download_count:,} downloads\n"
            stats_text += "\n"
        
        # Show file types if available
        file_types = stats.get('file_types', {})
        if file_types:
            stats_text += "<b>📁 ғɪʟᴇ ᴛʏᴘᴇs:</b>\n"
            for file_type, count in sorted(file_types.items(), key=lambda x: x[1], reverse=True)[:3]:
                stats_text += f"• {file_type.title()}: {count:,}\n"
            stats_text += "\n"
        
        stats_text += "<b>✅ sᴛᴀᴛᴜs:</b> ʙᴏᴛ ɪs ᴡᴏʀᴋɪɴɢ!"
        
        await message.reply_text(stats_text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        print(f"❌ Error in stats command: {e}")
        await message.reply_text(
            "<b>❌ ᴇʀʀᴏʀ ʟᴏᴀᴅɪɴɢ sᴛᴀᴛɪsᴛɪᴄs</b>",
            parse_mode=ParseMode.HTML
        )

async def get_stats():
    """Get bot statistics"""
    try:
        stats = await database.stats_data.find_one({"_id": "bot_stats"})
        if not stats:
            return {
                "total_downloads": 0,
                "total_file_size": 0,
                "sites": {},
                "top_users": {},
                "file_types": {}
            }
        return stats
    except Exception as e:
        print(f"❌ Error getting stats: {e}")
        return {
            "total_downloads": 0,
            "total_file_size": 0,
            "sites": {},
            "top_users": {},
            "file_types": {}
        }

async def get_user(user_id: int):
    """Get user data from database"""
    try:
        user = await database.user_data.find_one({"_id": user_id})
        if not user:
            # Return default user data
            return {
                "_id": user_id,
                "username": "",
                "first_name": "",
                "total_downloads": 0,
                "total_size": 0,
                "favorite_sites": {},
                "join_date": datetime.now(),
                "last_activity": datetime.now()
            }
        return user
    except Exception as e:
        print(f"❌ Error getting user {user_id}: {e}")
        return {
            "_id": user_id,
            "username": "",
            "first_name": "",
            "total_downloads": 0,
            "total_size": 0,
            "favorite_sites": {},
            "join_date": datetime.now(),
            "last_activity": datetime.now()
        }

async def get_user_rank(user_id: int):
    """Get user's rank based on total downloads"""
    try:
        user = await get_user(user_id)
        user_downloads = user.get('total_downloads', 0)
        
        # Count users with more downloads
        higher_users = await database.user_data.count_documents({
            'total_downloads': {'$gt': user_downloads}
        })
        
        return higher_users + 1
    except Exception as e:
        print(f"❌ Error getting user rank for {user_id}: {e}")
        return 0

async def get_user_download_history(user_id: int, limit: int = 10):
    """Get user's download history"""
    try:
        history = []
        async for entry in database.download_history.find({'user_id': user_id}).sort('download_time', -1).limit(limit):
            history.append(entry)
        return history
    except Exception as e:
        print(f"❌ Error getting download history for user {user_id}: {e}")
        return []

@Client.on_message(filters.command("mystats") & filters.private)
async def mystats_command(client: Client, message: Message):
    """Show user's personal statistics - FIXED VERSION"""
    try:
        user_id = message.from_user.id
        username = message.from_user.first_name or message.from_user.username or "Unknown"
        
        # Register/update user
        await register_new_user(user_id, username, message.from_user.first_name or "")
        
        # Get user data from database
        user = await get_user(user_id)
        
        # Get user's download history to verify data
        history = await get_user_download_history(user_id, 100)
        history_count = len(history) if history else 0
        
        # Check if stats need to be recalculated
        db_downloads = user.get('total_downloads', 0)
        if db_downloads == 0 and history_count > 0:
            # Stats are out of sync, show warning
            mystats_text = (
                f"<b>📊 ʏᴏᴜʀ sᴛᴀᴛɪsᴛɪᴄs</b>\n\n"
                f"<b>👤 ɴᴀᴍᴇ:</b> {username}\n"
                f"<b>🆔 ᴜsᴇʀ ɪᴅ:</b> <code>{user_id}</code>\n\n"
                f"⚠️ <b>sᴛᴀᴛs ᴏᴜᴛ ᴏғ sʏɴᴄ!</b>\n"
                f"📋 <b>ʜɪsᴛᴏʀʏ ʀᴇᴄᴏʀᴅs:</b> {history_count}\n"
                f"📊 <b>ᴅᴀᴛᴀʙᴀsᴇ sᴛᴀᴛs:</b> {db_downloads}\n\n"
                f"💡 <b>ᴜsᴇ /fixstats ᴛᴏ ʀᴇᴘᴀɪʀ!</b>"
            )
        else:
            # Normal stats display
            user_rank = await get_user_rank(user_id)
            
            def format_size(size_bytes):
                if size_bytes == 0:
                    return "0 B"
                size_names = ["B", "KB", "MB", "GB", "TB"]
                import math
                i = int(math.floor(math.log(size_bytes, 1024)))
                p = math.pow(1024, i)
                s = round(size_bytes / p, 2)
                return f"{s} {size_names[i]}"
            
            mystats_text = f"<b>📊 ʏᴏᴜʀ sᴛᴀᴛɪsᴛɪᴄs</b>\n\n"
            mystats_text += f"<b>👤 ɴᴀᴍᴇ:</b> {username}\n"
            mystats_text += f"<b>🆔 ᴜsᴇʀ ɪᴅ:</b> <code>{user_id}</code>\n"
            mystats_text += f"<b>📥 ᴛᴏᴛᴀʟ ᴅᴏᴡɴʟᴏᴀᴅs:</b> {user.get('total_downloads', 0):,}\n"
            mystats_text += f"<b>💾 ᴛᴏᴛᴀʟ sɪᴢᴇ:</b> {format_size(user.get('total_size', 0))}\n"
            mystats_text += f"<b>🏆 ʀᴀɴᴋ:</b> #{user_rank}\n"
            mystats_text += f"<b>📅 ᴊᴏɪɴᴇᴅ:</b> {user.get('join_date', datetime.now()).strftime('%Y-%m-%d')}\n\n"
            
            # Show favorite sites
            favorite_sites = user.get('favorite_sites', {})
            if favorite_sites:
                mystats_text += "<b>🌐 ғᴀᴠᴏʀɪᴛᴇ sɪᴛᴇs:</b>\n"
                top_sites = sorted(favorite_sites.items(), key=lambda x: x[1], reverse=True)[:3]
                for site, count in top_sites:
                    mystats_text += f"• {site}: {count:,}\n"
                mystats_text += "\n"
            
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
        
        # Just ensure user exists - don't try to update username/first_name
        user = await get_user(user_id)
        
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
        
        # Format file size helper
        def format_size(size_bytes):
            if size_bytes == 0:
                return "0 B"
            size_names = ["B", "KB", "MB", "GB", "TB"]
            import math
            i = int(math.floor(math.log(size_bytes, 1024)))
            p = math.pow(1024, i)
            s = round(size_bytes / p, 2)
            return f"{s} {size_names[i]}"
        
        history_text = f"<b>📋 ʏᴏᴜʀ ᴅᴏᴡɴʟᴏᴀᴅ ʜɪsᴛᴏʀʏ</b>\n\n"
        
        for i, item in enumerate(history, 1):
            date = item.get('download_time', datetime.now()).strftime('%Y-%m-%d %H:%M')
            site = item.get('site', 'Unknown')
            file_size = format_size(item.get('file_size', 0))
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
        history_text += f"<b>📊 sᴜᴍᴍᴀʀʏ:</b> {total_downloads} downloads • {format_size(total_size)}"
        
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
        
        # Just ensure user exists - don't try to update username/first_name
        user = await get_user(user_id)
        
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
        
        # Format file size helper
        def format_size(size_bytes):
            if size_bytes == 0:
                return "0 B"
            size_names = ["B", "KB", "MB", "GB", "TB"]
            import math
            i = int(math.floor(math.log(size_bytes, 1024)))
            p = math.pow(1024, i)
            s = round(size_bytes / p, 2)
            return f"{s} {size_names[i]}"
        
        leaderboard_text = f"<b>🏆 ᴛᴏᴘ ᴅᴏᴡɴʟᴏᴀᴅᴇʀs</b>\n\n"
        
        medals = ["🥇", "🥈", "🥉"]
        
        for i, user in enumerate(top_users, 1):
            username_display = user.get('username', user.get('first_name', 'Unknown'))
            downloads = user.get('total_downloads', 0)
            total_size = format_size(user.get('total_size', 0))
            
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
            total_size = format_size(current_user.get('total_size', 0))
            
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


# Helper function to get top users from database
async def get_top_users(limit: int = 10):
    """Get top users by download count"""
    try:
        users = []
        async for user in database.user_data.find({}).sort('total_downloads', -1).limit(limit):
            users.append(user)
        return users
    except Exception as e:
        print(f"❌ Error getting top users: {e}")
        return []

# Enhanced function to get user download history with better data
async def get_user_download_history(user_id: int, limit: int = 10):
    """Get user's download history with enhanced data"""
    try:
        history = []
        async for entry in database.download_history.find({'user_id': user_id}).sort('download_time', -1).limit(limit):
            history.append(entry)
        return history
    except Exception as e:
        print(f"❌ Error getting download history for user {user_id}: {e}")
        return []


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

@Client.on_message(filters.command("force_meet") & filters.create(check_admin))
async def force_meet_channels(client: Client, message: Message):
    """Force the bot to meet channels using alternative methods"""
    args = message.text.split()[1:]
    if not args:
        await message.reply_text(
            "<b>ᴜsᴀɢᴇ:</b> <code>/force_meet &lt;channel_id1&gt; &lt;channel_id2&gt; ...</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    results = []
    
    for channel_id in args:
        try:
            channel_id = int(channel_id)
            
            # Try multiple methods
            methods = [
                ("ɢᴇᴛ_ᴄʜᴀᴛ", lambda: client.get_chat(channel_id)),
                ("ʀᴇsᴏʟᴠᴇ_ᴘᴇᴇʀ", lambda: client.resolve_peer(channel_id)),
                ("ɢᴇᴛ_ᴄʜᴀᴛ_ᴍᴇᴍʙᴇʀ", lambda: client.get_chat_member(channel_id, client.me.id)),
            ]
            
            success = False
            for method_name, method_func in methods:
                try:
                    await method_func()
                    results.append(f"✅ {channel_id}: sᴜᴄᴄᴇss ᴠɪᴀ {method_name}")
                    success = True
                    break
                except Exception:
                    continue
            
            if not success:
                results.append(f"❌ {channel_id}: ᴀʟʟ ᴍᴇᴛʜᴏᴅs ғᴀɪʟᴇᴅ")
                
        except ValueError:
            results.append(f"❌ {channel_id}: ɪɴᴠᴀʟɪᴅ ᴄʜᴀɴɴᴇʟ ɪᴅ ғᴏʀᴍᴀᴛ")
        except Exception as e:
            results.append(f"❌ {channel_id}: {str(e)}")
    
    result_text = "<b>🔧 ғᴏʀᴄᴇ ᴍᴇᴇᴛ ʀᴇsᴜʟᴛs:</b>\n\n" + "\n".join(results)
    await message.reply_text(result_text, parse_mode=ParseMode.HTML)

@Client.on_message(filters.command("reset_stats") & filters.create(check_admin))
async def reset_stats_command(client: Client, message: Message):
    """Reset all statistics (admin only)"""
    try:
        # Create backup
        stats = load_stats()
        backup_file = f"stats_backup_{int(time.time())}.json"
        
        with open(backup_file, 'w') as f:
            json.dump(stats, f, indent=2)
        
        # Reset stats
        new_stats = {
            "total_downloads": 0,
            "users": {},
            "sites": {},
            "daily_stats": {},
            "file_types": {}
        }
        
        save_stats(new_stats)
        
        await message.reply_text(
            f"<b>✅ sᴛᴀᴛɪsᴛɪᴄs ʀᴇsᴇᴛ!</b>\n\n"
            f"<b>📁 ʙᴀᴄᴋᴜᴘ sᴀᴠᴇᴅ:</b> <code>{backup_file}</code>\n"
            f"<b>🔄 ᴀʟʟ sᴛᴀᴛs ʜᴀᴠᴇ ʙᴇᴇɴ ʀᴇsᴇᴛ</b>",
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        print(f"❌ Error resetting stats: {e}")
        await message.reply_text(
            "<b>❌ ᴇʀʀᴏʀ ʀᴇsᴇᴛᴛɪɴɢ sᴛᴀᴛɪsᴛɪᴄs</b>",
            parse_mode=ParseMode.HTML
        )

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

# Add this import at the top
from database import get_watermark_settings, update_watermark_settings

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

@Client.on_message(filters.command("logs") & filters.private & filters.create(check_admin))
async def logs_command(client: Client, message: Message):
    """Send recent logs to admin"""
    try:
        # Get recent active downloads info
        logs_text = "<b>📋 ʙᴏᴛ ʟᴏɢs</b>\n\n"
        
        if active_downloads:
            logs_text += f"<b>🔄 ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅs ({len(active_downloads)}):</b>\n"
            for user_id, tracker in active_downloads.items():
                logs_text += f"• ᴜsᴇʀ {user_id}: {tracker.status}\n"
            logs_text += "\n"
        else:
            logs_text += "<b>✅ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴅᴏᴡɴʟᴏᴀᴅs</b>\n\n"
        
        # System info
        import psutil
        cpu_percent = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        logs_text += f"<b>💻 sʏsᴛᴇᴍ ɪɴғᴏ:</b>\n"
        logs_text += f"• ᴄᴘᴜ: {cpu_percent}%\n"
        logs_text += f"• ʀᴀᴍ: {memory.percent}% ({format_bytes(memory.used)}/{format_bytes(memory.total)})\n"
        logs_text += f"• ᴅɪsᴋ: {disk.percent}% ({format_bytes(disk.used)}/{format_bytes(disk.total)})\n\n"
        
        # Dump channels status
        logs_text += f"<b>📁 ᴅᴜᴍᴘ ᴄʜᴀɴɴᴇʟs:</b>\n"
        for i, dump_id in enumerate(DUMP_CHAT_IDS, 1):
            try:
                chat = await client.get_chat(dump_id)
                logs_text += f"• ᴄʜᴀɴɴᴇʟ {i}: ✅ {chat.title}\n"
            except Exception as e:
                logs_text += f"• ᴄʜᴀɴɴᴇʟ {i}: ❌ {str(e)[:30]}...\n"
        
        await message.reply_text(logs_text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        print(f"❌ Error in logs command: {e}")
        await message.reply_text(
            f"<b>❌ ᴇʀʀᴏʀ ɢᴇᴛᴛɪɴɢ ʟᴏɢs:</b> <code>{str(e)}</code>",
            parse_mode=ParseMode.HTML
        )

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

# @Client.on_message(filters.command("test") & filters.private & filters.create(check_admin))
# async def test_command(client: Client, message: Message):
#     """Test bot functionality (admin only)"""
#     try:
#         test_results = []
        
#         # Test 1: Database connection
#         try:
#             user_count = await get_user_count()
#             test_results.append(f"✅ ᴅᴀᴛᴀʙᴀsᴇ: {user_count} ᴜsᴇʀs")
#         except Exception as e:
#             test_results.append(f"❌ ᴅᴀᴛᴀʙᴀsᴇ: {str(e)[:30]}...")
        
#         # Test 2: Dump channels
#         working_dumps = 0
#         for i, dump_id in enumerate(DUMP_CHAT_IDS, 1):
#             try:
#                 chat = await client.get_chat(dump_id)
#                 working_dumps += 1
#             except:
#                 pass
        
#         test_results.append(f"✅ ᴅᴜᴍᴘ ᴄʜᴀɴɴᴇʟs: {working_dumps}/{len(DUMP_CHAT_IDS)} ᴡᴏʀᴋɪɴɢ")
        
#         # Test 3: YT-DLP
#         try:
#             import yt_dlp
#             test_results.append("✅ ʏᴛ-ᴅʟᴘ: ɪɴsᴛᴀʟʟᴇᴅ")
#         except ImportError:
#             test_results.append("❌ ʏᴛ-ᴅʟᴘ: ɴᴏᴛ ɪɴsᴛᴀʟʟᴇᴅ")
        
#         # Test 4: FFmpeg
#         try:
#             process = await asyncio.create_subprocess_exec(
#                 'ffmpeg', '-version',
#                 stdout=asyncio.subprocess.DEVNULL,
#                 stderr=asyncio.subprocess.DEVNULL
#             )
#             await process.communicate()
#             if process.returncode == 0:
#                 test_results.append("✅ ғғᴍᴘᴇɢ: ɪɴsᴛᴀʟʟᴇᴅ")
#             else:
#                 test_results.append("❌ ғғᴍᴘᴇɢ: ɴᴏᴛ ᴡᴏʀᴋɪɴɢ")
#         except:
#             test_results.append("❌ ғғᴍᴘᴇɢ: ɴᴏᴛ ғᴏᴜɴᴅ")
        
#         # Test 5: Watermark settings
#         try:
#             watermark_settings = await get_watermark_settings()
#             status = "ᴇɴᴀʙʟᴇᴅ" if watermark_settings.get('enabled') else "ᴅɪsᴀʙʟᴇᴅ"
#             test_results.append(f"✅ ᴡᴀᴛᴇʀᴍᴀʀᴋ: {status}")
#         except Exception as e:
#             test_results.append(f"❌ ᴡᴀᴛᴇʀᴍᴀʀᴋ: {str(e)[:30]}...")
        
#         test_text = "<b>🧪 ʙᴏᴛ ᴛᴇsᴛ ʀᴇsᴜʟᴛs</b>\n\n" + "\n".join(test_results)
