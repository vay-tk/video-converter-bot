import asyncio
import re
import logging
import time
from pathlib import Path
from typing import Optional, Callable
import subprocess

logger = logging.getLogger(__name__)

class FFmpegConverter:
    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path
        self.last_progress = {}  # Track last progress per conversion
    
    async def convert_to_mp4(
        self, 
        input_path: Path, 
        output_path: Path,
        progress_callback: Optional[Callable] = None
    ) -> bool:
        """Convert video to MP4 (H.264 + AAC)"""
        cmd = [
            self.ffmpeg_path,
            "-i", str(input_path),
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "medium",
            "-crf", "23",
            "-map", "0:v:0",  # First video stream
            "-map", "0:a:0?",  # First audio stream (optional)
            "-map", "0:s:0?",  # First subtitle stream (optional)
            "-movflags", "+faststart",
            "-progress", "pipe:1",  # Send progress to stdout
            "-loglevel", "error",    # Reduce stderr noise
            "-y",
            str(output_path)
        ]
        
        return await self._run_ffmpeg(cmd, progress_callback, "mp4")
    
    async def convert_to_mkv(
        self,
        input_path: Path,
        output_path: Path,
        progress_callback: Optional[Callable] = None
    ) -> bool:
        """Convert video to MKV (H.265 + AAC, 480p, CRF 28)"""
        cmd = [
            self.ffmpeg_path,
            "-i", str(input_path),
            "-c:v", "libx265",
            "-crf", "28",
            "-preset", "medium",
            "-vf", "scale=-2:480",  # Resize to 480p, maintain aspect ratio
            "-c:a", "aac",
            "-b:a", "96k",
            "-map", "0:v:0",  # First video stream
            "-map", "0:a",    # All audio streams
            "-map", "0:s?",   # All subtitle streams (optional)
            "-progress", "pipe:1",  # Send progress to stdout
            "-loglevel", "error",    # Reduce stderr noise
            "-y",
            str(output_path)
        ]
        
        return await self._run_ffmpeg(cmd, progress_callback, "mkv")
    
    async def _run_ffmpeg(
        self, 
        cmd: list, 
        progress_callback: Optional[Callable] = None,
        conversion_id: str = "default"
    ) -> bool:
        """Execute FFmpeg command with progress tracking"""
        try:
            logger.info(f"Starting FFmpeg conversion: {' '.join(cmd[:3])}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Initialize progress tracking for this conversion
            self.last_progress[conversion_id] = {
                'percent': -1,
                'last_update': 0,
                'start_time': time.time()
            }
            
            # Monitor progress if callback provided
            progress_task = None
            if progress_callback:
                progress_task = asyncio.create_task(
                    self._monitor_progress(process.stdout, progress_callback, conversion_id)
                )
            
            # Wait for process completion
            stdout, stderr = await process.communicate()
            
            # Cancel progress monitoring if it's still running
            if progress_task and not progress_task.done():
                progress_task.cancel()
                try:
                    await progress_task
                except asyncio.CancelledError:
                    pass
            
            # Cleanup progress tracking
            if conversion_id in self.last_progress:
                del self.last_progress[conversion_id]
            
            if process.returncode == 0:
                logger.info("FFmpeg conversion successful")
                return True
            else:
                error_msg = stderr.decode().strip()
                logger.error(f"FFmpeg failed: {error_msg}")
                return False
                
        except Exception as e:
            logger.error(f"FFmpeg execution error: {e}")
            return False
    
    async def _monitor_progress(
        self, 
        stream: asyncio.StreamReader,
        callback: Callable,
        conversion_id: str
    ):
        """Monitor FFmpeg progress output from stdout"""
        try:
            buffer = ""
            while True:
                try:
                    # Read with timeout to prevent hanging
                    data = await asyncio.wait_for(stream.read(1024), timeout=2.0)
                    if not data:
                        break
                    
                    buffer += data.decode('utf-8', errors='ignore')
                    lines = buffer.split('\n')
                    buffer = lines[-1]  # Keep incomplete line
                    
                    for line in lines[:-1]:
                        line = line.strip()
                        await self._parse_progress_line(line, callback, conversion_id)
                                
                except asyncio.TimeoutError:
                    continue  # Continue reading if no data available
                except Exception as e:
                    logger.debug(f"Progress reading error: {e}")
                    break
                    
        except Exception as e:
            logger.debug(f"Progress monitoring stopped: {e}")
    
    async def _parse_progress_line(self, line: str, callback: Callable, conversion_id: str):
        """Parse FFmpeg progress line and call callback if significant change"""
        try:
            progress_info = self.last_progress.get(conversion_id, {})
            current_time = time.time()
            
            if line.startswith('out_time_ms='):
                try:
                    microseconds = int(line.split('=')[1])
                    current_seconds = microseconds / 1000000
                    
                    # Get duration for percentage calculation
                    if hasattr(self, '_current_duration') and self._current_duration:
                        percent = min((current_seconds / self._current_duration) * 100, 100)
                        
                        # Only update if significant change (>2%) or enough time passed (>10s)
                        last_percent = progress_info.get('percent', -1)
                        last_update = progress_info.get('last_update', 0)
                        
                        if (abs(percent - last_percent) >= 2 or 
                            current_time - last_update >= 10):
                            
                            # Calculate ETA
                            elapsed = current_time - progress_info.get('start_time', current_time)
                            eta_text = ""
                            if elapsed > 60 and percent > 5:  # Calculate ETA after 1 minute and >5%
                                remaining_percent = 100 - percent
                                eta_seconds = (elapsed / percent) * remaining_percent
                                eta_text = f" | ETA: {self._format_time(eta_seconds)}"
                            
                            # Update progress tracking
                            self.last_progress[conversion_id].update({
                                'percent': percent,
                                'last_update': current_time
                            })
                            
                            # Call callback with formatted progress
                            await callback(percent, current_seconds, eta_text)
                            
                except (ValueError, IndexError, ZeroDivisionError):
                    pass
                    
        except Exception as e:
            logger.debug(f"Progress parsing error: {e}")
    
    def _format_time(self, seconds: float) -> str:
        """Format seconds into human readable time"""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m {int(seconds % 60)}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"
    
    async def get_video_duration(self, file_path: Path) -> Optional[float]:
        """Get video duration in seconds"""
        try:
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                str(file_path)
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, _ = await process.communicate()
            
            if process.returncode == 0:
                duration = float(stdout.decode().strip())
                self._current_duration = duration  # Store for progress calculation
                logger.info(f"Video duration: {self._format_time(duration)}")
                return duration
            
        except Exception as e:
            logger.error(f"Duration detection error: {e}")
        
        return None