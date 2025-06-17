import os
import re
import time
import shutil
from urllib.parse import urlparse

def is_valid_url(url):
    """Validate URL format"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def format_bytes(bytes_value):
    """Format bytes to human readable format"""
    if not bytes_value:
        return "0 B"
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024
    return f"{bytes_value:.1f} PB"

def format_duration(seconds):
    """Format duration in seconds to human readable format"""
    if not seconds:
        return "Unknown"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"

def clean_filename(filename):
    """Clean filename for safe file operations"""
    # Remove invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Limit length
    if len(filename) > 200:
        name, ext = os.path.splitext(filename)
        filename = name[:200-len(ext)] + ext
    return filename

def cleanup_directory(directory_path, max_age_hours=1):
    """Clean up old directories"""
    try:
        if not os.path.exists(directory_path):
            return
        
        current_time = time.time()
        for item in os.listdir(directory_path):
            item_path = os.path.join(directory_path, item)
            if os.path.isdir(item_path):
                creation_time = os.path.getctime(item_path)
                age_hours = (current_time - creation_time) / 3600
                
                if age_hours > max_age_hours:
                    shutil.rmtree(item_path)
                    print(f"Cleaned up old directory: {item}")
    except Exception as e:
        print(f"Error cleaning up directory: {e}")

def get_file_type(file_path):
    """Determine file type based on extension"""
    ext = os.path.splitext(file_path)[1].lower()
    
    video_exts = ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv', '.m4v']
    audio_exts = ['.mp3', '.m4a', '.wav', '.flac', '.ogg', '.aac', '.wma']
    image_exts = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
    
    if ext in video_exts:
        return 'video'
    elif ext in audio_exts:
        return 'audio'
    elif ext in image_exts:
        return 'image'
    else:
        return 'document'

def create_progress_bar(progress, length=10):
    """Create a progress bar string"""
    filled = int(length * progress / 100)
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}]"


import os
import logging
import time

LOGGER = logging.getLogger(__name__)

def cleanup_directory(directory, max_age_hours=1):
    """Clean up old files in directory"""
    try:
        if not os.path.exists(directory):
            return
        
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            if os.path.isfile(file_path):
                file_age = current_time - os.path.getmtime(file_path)
                if file_age > max_age_seconds:
                    os.remove(file_path)
                    LOGGER.info(f"Cleaned up old file: {filename}")
                    
    except Exception as e:
        LOGGER.error(f"Error in cleanup_directory: {e}")

def setup_directories():
    """Setup required directories"""
    try:
        from config import Config
        os.makedirs(Config.DOWNLOAD_DIR, exist_ok=True)
        LOGGER.info(f"✅ Download directory ready: {Config.DOWNLOAD_DIR}")
        return True
    except Exception as e:
        LOGGER.error(f"❌ Error creating directories: {e}")
        return False
