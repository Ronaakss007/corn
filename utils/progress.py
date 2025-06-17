import time
import asyncio
from .helpers import format_bytes, create_progress_bar

class ProgressTracker:
    def __init__(self):
        self.downloaded_bytes = 0
        self.total_size = 0
        self.download_speed = 0
        self.eta = 0
        self.progress = 0
        self.start_time = time.time()
        self.last_update = 0
        
    def update(self, downloaded, total, speed=0, eta=0):
        """Update progress values"""
        self.downloaded_bytes = downloaded
        self.total_size = total
        self.download_speed = speed
        self.eta = eta
        
        if total > 0:
            self.progress = (downloaded / total) * 100
        
        self.last_update = time.time()
    
    def get_progress_text(self):
        """Get formatted progress text"""
        progress_bar = create_progress_bar(self.progress)
        speed_str = format_bytes(self.download_speed) + "/s" if self.download_speed else "0 B/s"
        downloaded_str = format_bytes(self.downloaded_bytes)
        total_str = format_bytes(self.total_size) if self.total_size else "Unknown"
        
        elapsed_time = time.time() - self.start_time
        elapsed_str = f"{int(elapsed_time//60)}:{int(elapsed_time%60):02d}"
        
        eta_str = f"{int(self.eta//60)}:{int(self.eta%60):02d}" if self.eta > 0 else "Unknown"
        
        text = f"📥 **Downloading...**\n\n"
        text += f"{progress_bar} {self.progress:.1f}%\n\n"
        text += f"📊 **Downloaded:** {downloaded_str} / {total_str}\n"
        text += f"⚡ **Speed:** {speed_str}\n"
        text += f"⏱️ **Elapsed:** {elapsed_str}\n"
        text += f"🕐 **ETA:** {eta_str}"
        
        return text
