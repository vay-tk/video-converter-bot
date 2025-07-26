# c:\Users\vm\Desktop\video converter bot\utils\file_manager.py
import os
import asyncio
import aiofiles
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class FileManager:
    def __init__(self, temp_dir: str):
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(exist_ok=True)
    
    def get_temp_path(self, filename: str, suffix: str = "") -> Path:
        """Generate unique temporary file path"""
        base_name = Path(filename).stem
        extension = Path(filename).suffix
        temp_filename = f"{base_name}{suffix}{extension}"
        return self.temp_dir / temp_filename
    
    async def download_file(self, message, progress_callback=None) -> Optional[Path]:
        """Download file from Telegram message"""
        try:
            if message.video:
                file_info = message.video
            elif message.document:
                file_info = message.document
            else:
                return None
            
            file_name = getattr(file_info, 'file_name', f"video_{file_info.file_id}.mp4")
            temp_path = self.get_temp_path(file_name, "_input")
            
            await message.download(
                file_name=str(temp_path),
                progress=progress_callback
            )
            
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