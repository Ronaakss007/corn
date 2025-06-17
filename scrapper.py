import asyncio
import os
import time
import logging
from secrets import token_urlsafe
import yt_dlp
from utils.helpers import create_progress_bar
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import Config
from utils.helpers import is_valid_url, format_bytes, format_duration, clean_filename, get_file_type
from utils.progress import ProgressTracker

LOGGER = logging.getLogger(__name__)

class YtDlpScrapper:
    def __init__(self, client, message):
        self.client = client
        self.message = message
        self.user_id = message.from_user.id
        self.chat_id = message.chat.id
        self.link = ""
        self.name = ""
        self.gid = token_urlsafe(10)
        self.is_cancelled = False
        self.formats = {}
        self.selected_quality = None
        self.download_path = f"{Config.DOWNLOAD_DIR}{self.gid}/"
        self.progress_tracker = ProgressTracker()
        self.downloaded_file = None
        
        # Create download directory
        os.makedirs(self.download_path, exist_ok=True)

    async def start_leech(self):
        """Main entry point for leech command"""
        try:
            # Check authorization
            if not Config.is_authorized(self.user_id):
                await self.message.reply("❌ You're not authorized to use this bot!")
                return
            
            # Parse command and extract link
            command_parts = self.message.text.split(maxsplit=1)
            if len(command_parts) < 2:
                help_text = (
                    "🤖 **YT-DLP Leech Bot**\n\n"
                    "📝 **Usage:** `/yl1 <URL>`\n\n"
                    "🌐 **Supported Sites:**\n"
                    "• YouTube\n• Pornhub\n• Xvideos\n• Instagram\n"
                    "• TikTok\n• Twitter\n• And 1000+ more!\n\n"
                    "📋 **Example:**\n"
                    "`/yl1 https://www.youtube.com/watch?v=VIDEO_ID`"
                )
                await self.message.reply(help_text)
                return
                
            self.link = command_parts[1].strip()
            
            # Validate URL
            if not is_valid_url(self.link):
                await self.message.reply("❌ Invalid URL provided! Please provide a valid HTTP/HTTPS URL.")
                return
            
            # Extract video info
            status_msg = await self.message.reply("🔍 **Extracting video information...**\n\n⏳ Please wait...")
            
            video_info = await self._extract_info()
            if not video_info:
                await status_msg.edit_text("❌ Could not extract video information!")
                return
                
            # Show quality selection
            await self._show_quality_selection(video_info, status_msg)
            
        except Exception as e:
            LOGGER.error(f"Error in start_leech: {e}")
            await self.message.reply(f"❌ Error: {str(e)}")
            self._cleanup()

    async def _extract_info(self):
        """Extract video information using yt-dlp"""
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'ignoreerrors': True,
                'age_limit': 21,  # Bypass age restrictions
                'nocheckcertificate': True,
            }
            
            def extract():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(self.link, download=False)
            
            # Run in thread to avoid blocking
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, extract)
            
            if not info:
                LOGGER.error("No video information extracted")
                return None
                
            return info
            
        except Exception as e:
            LOGGER.error(f"Error extracting info: {e}")
            return None

    async def _show_quality_selection(self, video_info, status_msg):
        """Show quality selection buttons"""
        try:
            self.formats = {}
            buttons = []
            
            # Get video title and info
            title = video_info.get('title', 'Unknown Title')
            duration = video_info.get('duration', 0)
            uploader = video_info.get('uploader', 'Unknown')
            view_count = video_info.get('view_count', 0)
            
            # Handle playlist
            if 'entries' in video_info:
                entry_count = len([e for e in video_info['entries'] if e])
                
                # For playlists, show standard quality options
                qualities = ['1080', '720', '480', '360', '240', '144']
                for quality in qualities:
                    format_code = f"bv*[height<={quality}]+ba/b[height<={quality}]"
                    self.formats[f"{quality}p"] = format_code
                    buttons.append([InlineKeyboardButton(f"📹 {quality}p", callback_data=f"yl_qual_{self.gid}_{quality}p")])
                
                # Add audio options for playlist
                self.formats['mp3_128'] = 'bestaudio[ext=m4a]/bestaudio'
                self.formats['mp3_320'] = 'bestaudio[ext=m4a]/bestaudio'
                buttons.extend([
                    [InlineKeyboardButton("🎵 MP3 128kbps", callback_data=f"yl_qual_{self.gid}_mp3_128")],
                    [InlineKeyboardButton("🎵 MP3 320kbps", callback_data=f"yl_qual_{self.gid}_mp3_320")]
                ])
                
                info_text = f"📹 **Playlist Found!**\n\n"
                info_text += f"**Title:** {title[:60]}{'...' if len(title) > 60 else ''}\n"
                info_text += f"**Videos:** {entry_count}\n"
                info_text += f"**Uploader:** {uploader}\n\n"
                info_text += "🎯 **Select Quality for all videos:**"
                
            else:
                # For single videos, extract available formats
                formats = video_info.get('formats', [])
                video_formats = {}
                audio_formats = {}
                
                for fmt in formats:
                    format_id = fmt.get('format_id', '')
                    ext = fmt.get('ext', 'unknown')
                    filesize = fmt.get('filesize') or fmt.get('filesize_approx', 0)
                    
                    if fmt.get('vcodec') != 'none' and fmt.get('height'):
                        # Video format
                        height = fmt['height']
                        fps = fmt.get('fps', '')
                        fps_str = f"{fps}fps" if fps else ""
                        
                        quality_key = f"{height}p-{ext}"
                        if fps_str:
                            quality_key += f"-{fps_str}"
                            
                        if quality_key not in video_formats or filesize > video_formats[quality_key]['size']:
                            video_formats[quality_key] = {
                                'format_id': format_id,
                                'size': filesize,
                                'height': height
                            }
                    
                    elif fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                        # Audio format
                        abr = fmt.get('abr', 0)
                        if abr:
                            audio_key = f"{int(abr)}kbps-{ext}"
                            if audio_key not in audio_formats or filesize > audio_formats[audio_key]['size']:
                                audio_formats[audio_key] = {
                                    'format_id': format_id,
                                    'size': filesize,
                                    'abr': abr
                                }
                
                # Sort video formats by quality (highest first)
                sorted_video = sorted(video_formats.items(), 
                                    key=lambda x: x[1]['height'], reverse=True)
                
                # Add video format buttons
                for quality_key, format_info in sorted_video[:8]:  # Limit to 8 options
                    size_str = f" ({format_bytes(format_info['size'])})" if format_info['size'] else ""
                    button_text = f"📹 {quality_key}{size_str}"
                    self.formats[quality_key] = format_info['format_id']
                    buttons.append([InlineKeyboardButton(button_text, callback_data=f"yl_qual_{self.gid}_{quality_key}")])
                
                # Sort audio formats by quality (highest first)
                sorted_audio = sorted(audio_formats.items(), 
                                    key=lambda x: x[1]['abr'], reverse=True)
                
                # Add audio format buttons
                for quality_key, format_info in sorted_audio[:4]:  # Limit to 4 options
                    size_str = f" ({format_bytes(format_info['size'])})" if format_info['size'] else ""
                    button_text = f"🎵 {quality_key}{size_str}"
                    self.formats[quality_key] = format_info['format_id']
                    buttons.append([InlineKeyboardButton(button_text, callback_data=f"yl_qual_{self.gid}_{quality_key}")])
                
                info_text = f"📹 **Video Found!**\n\n"
                info_text += f"**Title:** {title[:60]}{'...' if len(title) > 60 else ''}\n"
                info_text += f"**Duration:** {format_duration(duration)}\n"
                info_text += f"**Uploader:** {uploader}\n"
                if view_count:
                    info_text += f"**Views:** {view_count:,}\n"
                info_text += f"\n🎯 **Select Quality:**"
            
            # Add default options
            self.formats['best_video'] = 'bv*+ba/b'
            self.formats['best_audio'] = 'ba/b'
            self.formats['mp3_best'] = 'bestaudio[ext=m4a]/bestaudio'
            
            buttons.extend([
                [InlineKeyboardButton("🏆 Best Video", callback_data=f"yl_qual_{self.gid}_best_video")],
                [InlineKeyboardButton("🎵 Best Audio", callback_data=f"yl_qual_{self.gid}_best_audio")],
                [InlineKeyboardButton("🎵 MP3 Audio", callback_data=f"yl_qual_{self.gid}_mp3_best")],
                [InlineKeyboardButton("❌ Cancel", callback_data=f"yl_cancel_{self.gid}")]
            ])
            
            keyboard = InlineKeyboardMarkup(buttons)
            await status_msg.edit_text(info_text, reply_markup=keyboard)
            
        except Exception as e:
            LOGGER.error(f"Error showing quality selection: {e}")
            await status_msg.edit_text(f"❌ Error showing quality options: {str(e)}")

    async def start_download(self, quality):
        """Start the download process"""
        try:
            self.selected_quality = self.formats.get(quality, 'best')
            
            # Send download started message
            status_msg = await self.message.reply("📥 **Download Started!**\n\n⏳ Preparing download...")
            
            # Configure yt-dlp options
            ydl_opts = {
                'format': self.selected_quality,
                'outtmpl': f'{self.download_path}%(title)s.%(ext)s',
                'progress_hooks': [self._progress_hook],
                'quiet': True,
                'no_warnings': True,
                'writethumbnail': True,
                'writeinfojson': False,
                'ignoreerrors': True,
                'age_limit': 21,
                'nocheckcertificate': True,
                'extract_flat': False,
                'trim_file_name': 200,
                'retries': 3,
                'fragment_retries': 3,
            }
            
            # Add audio extraction for mp3
            if 'mp3' in quality.lower():
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '320' if '320' in quality else '192',
                }]
            
            # Add metadata postprocessor
            if 'postprocessors' not in ydl_opts:
                ydl_opts['postprocessors'] = []
            
            ydl_opts['postprocessors'].append({
                'key': 'FFmpegMetadata',
                'add_metadata': True,
            })
            
            # Start download in thread
            loop = asyncio.get_event_loop()
            download_task = loop.run_in_executor(None, self._download_video, ydl_opts)
            
            # Monitor progress
            await self._monitor_progress(status_msg, download_task)
            
        except Exception as e:
            LOGGER.error(f"Error in start_download: {e}")
            await self.message.reply(f"❌ Download failed: {str(e)}")
            self._cleanup()

    def _download_video(self, ydl_opts):
        """Download video using yt-dlp"""
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.link])
            return True
        except Exception as e:
            LOGGER.error(f"Download error: {e}")
            return False

    def _progress_hook(self, d):
        """Progress hook for yt-dlp"""
        if self.is_cancelled:
            raise Exception("Download cancelled by user")
            
        if d['status'] == 'downloading':
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
            speed = d.get('speed', 0) or 0
            eta = d.get('eta', 0) or 0
            
            self.progress_tracker.update(downloaded, total, speed, eta)
            
        elif d['status'] == 'finished':
            self.downloaded_file = d['filename']
            self.progress_tracker.progress = 100

    async def _monitor_progress(self, status_msg, download_task):
        """Monitor download progress and update status"""
        last_update = 0
        
        while not download_task.done():
            current_time = time.time()
            
            # Update every few seconds
            if current_time - last_update >= Config.PROGRESS_UPDATE_INTERVAL:
                try:
                    progress_text = self.progress_tracker.get_progress_text()
                    await status_msg.edit_text(progress_text)
                    last_update = current_time
                    
                except Exception as e:
                    LOGGER.error(f"Error updating progress: {e}")
            
            await asyncio.sleep(1)
        
        # Check download result
        download_success = await download_task
        
        if download_success and not self.is_cancelled:
            await self._upload_file(status_msg)
        else:
            await status_msg.edit_text("❌ Download failed or was cancelled!")
            self._cleanup()

    async def _upload_file(self, status_msg):
        """Upload downloaded file to Telegram"""
        try:
            await status_msg.edit_text("📤 **Upload Started!**\n\n⏳ Uploading to Telegram...")
            
            # Find downloaded files
            files = []
            for file in os.listdir(self.download_path):
                if not file.endswith(('.part', '.ytdl', '.temp', '.tmp')):
                    file_path = os.path.join(self.download_path, file)
                    if os.path.isfile(file_path):
                        files.append(file_path)
            
            if not files:
                await status_msg.edit_text("❌ No files found to upload!")
                return
            
            uploaded_count = 0
            
            # Upload each file
            for file_path in files:
                # Skip thumbnail files for now
                if file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')) and 'thumb' in file_path.lower():
                    continue
                
                file_size = os.path.getsize(file_path)
                file_name = os.path.basename(file_path)
                
                # Check file size (Telegram limit: 2GB)
                if file_size > Config.MAX_FILE_SIZE:
                    await status_msg.edit_text(
                        f"❌ **File too large!**\n\n"
                        f"📄 **File:** {file_name}\n"
                        f"💾 **Size:** {format_bytes(file_size)}\n"
                        f"⚠️ **Limit:** {format_bytes(Config.MAX_FILE_SIZE)}"
                    )
                    continue
                
                # Determine file type and upload accordingly
                file_type = get_file_type(file_path)
                caption = f"📄 **{file_name}**\n💾 **Size:** {format_bytes(file_size)}"
                
                try:
                    if file_type == 'video':
                        await self.message.reply_video(
                            video=file_path,
                            caption=caption,
                            supports_streaming=True,
                            progress=self._upload_progress,
                            progress_args=(status_msg, file_name)
                        )
                    elif file_type == 'audio':
                        await self.message.reply_audio(
                            audio=file_path,
                            caption=caption,
                            progress=self._upload_progress,
                            progress_args=(status_msg, file_name)
                        )
                    else:
                        await self.message.reply_document(
                            document=file_path,
                            caption=caption,
                            progress=self._upload_progress,
                            progress_args=(status_msg, file_name)
                        )
                    
                    uploaded_count += 1
                    
                except Exception as e:
                    LOGGER.error(f"Error uploading {file_name}: {e}")
                    await self.message.reply(f"❌ Failed to upload: {file_name}\nError: {str(e)}")
            
            if uploaded_count > 0:
                await status_msg.edit_text(
                    f"✅ **Upload Complete!**\n\n"
                    f"🎉 Successfully uploaded {uploaded_count} file(s)!"
                )
            else:
                await status_msg.edit_text("❌ No files were uploaded successfully!")
            
        except Exception as e:
            LOGGER.error(f"Error uploading file: {e}")
            await status_msg.edit_text(f"❌ Upload failed: {str(e)}")
        finally:
            self._cleanup()

    async def _upload_progress(self, current, total, status_msg, filename):
        """Upload progress callback"""
        try:
            if total > 0:
                progress = (current / total) * 100
                progress_bar = create_progress_bar(progress)
                
                text = f"📤 **Uploading...**\n\n"
                text += f"📄 **File:** {filename[:30]}{'...' if len(filename) > 30 else ''}\n"
                text += f"{progress_bar} {progress:.1f}%\n\n"
                text += f"📊 **Uploaded:** {format_bytes(current)} / {format_bytes(total)}"
                
                # Update every 5% or every 10 seconds
                if progress % 5 < 1 or time.time() - getattr(self, '_last_upload_update', 0) > 10:
                    await status_msg.edit_text(text)
                    self._last_upload_update = time.time()
                    
        except Exception as e:
            LOGGER.error(f"Error in upload progress: {e}")

    def _cleanup(self):
        """Clean up downloaded files and remove from active downloads"""
        try:
            # Remove downloaded files
            if os.path.exists(self.download_path):
                for file in os.listdir(self.download_path):
                    file_path = os.path.join(self.download_path, file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        LOGGER.info(f"Removed file: {file}")
                os.rmdir(self.download_path)
                LOGGER.info(f"Removed directory: {self.download_path}")
                
        except Exception as e:
            LOGGER.error(f"Error in cleanup: {e}")

    def cancel_download(self):
        """Cancel the download"""
        self.is_cancelled = True
        LOGGER.info(f"Download cancelled by user: {self.user_id}")
        self._cleanup()

# Additional utility functions for scrapper
def get_supported_sites():
    """Get list of supported sites"""
    return [
        "YouTube", "Pornhub", "Xvideos", "RedTube", "YouPorn",
        "Instagram", "TikTok", "Twitter", "Facebook", "Vimeo",
        "Dailymotion", "Twitch", "SoundCloud", "Bandcamp",
        "And 1000+ more sites supported by yt-dlp"
    ]

async def get_video_info_quick(url):
    """Quick video info extraction for previews"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
        }
        
        def extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, extract)
        
        if info:
            return {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'thumbnail': info.get('thumbnail', ''),
                'is_playlist': 'entries' in info
            }
    except:
        pass
    
    return None
