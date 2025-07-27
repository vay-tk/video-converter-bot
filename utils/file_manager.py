# c:\Users\vm\Desktop\video converter bot\utils\file_manager.py
import os
import asyncio
import aiofiles
import time
import re
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class FileManager:
    def __init__(self, temp_dir: str):
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(exist_ok=True)
    
    def sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to remove invalid characters"""
        # Remove or replace invalid characters for file systems
        sanitized = re.sub(r'[<>:"/\\|?*\[\]]', '_', filename)
        # Remove multiple underscores
        sanitized = re.sub(r'_+', '_', sanitized)
        # Remove leading/trailing dots and spaces
        sanitized = sanitized.strip(' .')
        # Limit length to prevent path too long errors
        if len(sanitized) > 200:
            name_part = sanitized[:190]
            ext_part = sanitized[-10:] if '.' in sanitized[-10:] else ''
            sanitized = name_part + ext_part
        
        return sanitized if sanitized else "video"
    
    def get_temp_path(self, filename: str, suffix: str = "") -> Path:
        """Generate unique temporary file path with sanitized filename"""
        # Sanitize the filename first
        clean_filename = self.sanitize_filename(filename)
        
        base_name = Path(clean_filename).stem
        extension = Path(clean_filename).suffix
        
        # Ensure we have an extension
        if not extension:
            extension = ".mp4"  # Default extension
        
        temp_filename = f"{base_name}{suffix}{extension}"
        return self.temp_dir / temp_filename
    
    async def download_file(self, message, progress_callback=None) -> Optional[Path]:
        """Download file from Telegram message with throttled progress updates"""
        try:
            if message.video:
                file_info = message.video
            elif message.document:
                file_info = message.document
            else:
                return None
            
            file_name = getattr(file_info, 'file_name', f"video_{file_info.file_id}.mp4")
            temp_path = self.get_temp_path(file_name, "_input")
            
            logger.info(f"Starting download: {file_name}")
            
            # Wrapper to throttle progress updates
            last_callback_time = 0
            
            async def throttled_progress(current, total):
                nonlocal last_callback_time
                
                if progress_callback:
                    current_time = time.time()
                    # Only call the callback every 5 seconds or at completion
                    if (current_time - last_callback_time >= 5 or 
                        current == total or 
                        last_callback_time == 0):
                        
                        await progress_callback(current, total)
                        last_callback_time = current_time
            
            await message.download(
                file_name=str(temp_path),
                progress=throttled_progress if progress_callback else None
            )
            
            logger.info(f"Download completed: {temp_path}")
            return temp_path
            
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return None
    
    def cleanup_file(self, file_path: Path):
        """Remove temporary file"""
        try:
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Cleaned up: {file_path}")
        except Exception as e:
            logger.error(f"Cleanup failed for {file_path}: {e}")
    
    def get_file_size(self, file_path: Path) -> int:
        """Get file size in bytes"""
        return file_path.stat().st_size if file_path.exists() else 0
