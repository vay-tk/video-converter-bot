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
        self.last_progress = {}
    
    async def convert_to_mp4(
        self, 
        input_path: Path, 
        output_path: Path,
        progress_callback: Optional[Callable] = None
    ) -> bool:
        """Convert video to MP4 (H.264 + AAC)"""
        # Get duration first for progress calculation
        duration = await self.get_video_duration(input_path)
        
        cmd = [
            self.ffmpeg_path,
            "-i", str(input_path),
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "medium",
            "-crf", "23",
            "-map", "0:v:0",
            "-map", "0:a:0?",
            "-map", "0:s:0?",
            "-movflags", "+faststart",
            "-progress", "pipe:2",  # Send progress to stderr
            "-nostats",             # Disable default stats
            "-y",
            str(output_path)
        ]
        
        return await self._run_ffmpeg(cmd, progress_callback, duration, "mp4")
    
    async def convert_to_mkv(
        self,
        input_path: Path,
        output_path: Path,
        progress_callback: Optional[Callable] = None
    ) -> bool:
        """Convert video to MKV (H.265 + AAC, 480p, CRF 28)"""
        # Get duration first for progress calculation
        duration = await self.get_video_duration(input_path)
        
        cmd = [
            self.ffmpeg_path,
            "-i", str(input_path),
            "-c:v", "libx265",
            "-crf", "28",
            "-preset", "medium",
            "-vf", "scale=-2:480",
            "-c:a", "aac",
            "-b:a", "96k",
            "-map", "0:v:0",
            "-map", "0:a",
            "-map", "0:s?",
            "-progress", "pipe:2",  # Send progress to stderr
            "-nostats",             # Disable default stats
            "-y",
            str(output_path)
        ]
        
        return await self._run_ffmpeg(cmd, progress_callback, duration, "mkv")
    
    async def _run_ffmpeg(
        self, 
        cmd: list, 
        progress_callback: Optional[Callable] = None,
        duration: Optional[float] = None,
        conversion_id: str = "default"
    ) -> bool:
        """Execute FFmpeg command with progress tracking"""
        try:
            logger.info(f"Starting FFmpeg conversion with duration: {duration}s")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Initialize progress tracking
            self.last_progress[conversion_id] = {
                'percent': 0,
                'last_update': time.time(),
                'start_time': time.time(),
                'last_message': ''
            }
            
            # Monitor progress if callback provided
            progress_task = None
            if progress_callback and duration:
                progress_task = asyncio.create_task(
                    self._monitor_progress_simple(process.stderr, progress_callback, duration, conversion_id)
                )
            
            # Wait for process completion
            stdout, stderr = await process.communicate()
            
            # Cancel progress monitoring
            if progress_task and not progress_task.done():
                progress_task.cancel()
                try:
                    await progress_task
                except asyncio.CancelledError:
                    pass
            
            # Cleanup
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
    
    async def _monitor_progress_simple(
        self, 
        stderr_stream: asyncio.StreamReader,
        callback: Callable,
        total_duration: float,
        conversion_id: str
    ):
        """Simple progress monitoring that actually works"""
        try:
            progress_info = self.last_progress[conversion_id]
            
            while True:
                try:
                    line = await asyncio.wait_for(stderr_stream.readline(), timeout=5.0)
                    if not line:
                        break
                    
                    line = line.decode('utf-8', errors='ignore').strip()
                    
                    # Look for time progress in format "out_time_us=123456789"
                    if 'out_time_us=' in line:
                        try:
                            time_match = re.search(r'out_time_us=(\d+)', line)
                            if time_match:
                                microseconds = int(time_match.group(1))
                                current_seconds = microseconds / 1000000
                                
                                # Calculate percentage
                                percent = min((current_seconds / total_duration) * 100, 100)
                                
                                # Update every 5% or every 30 seconds
                                current_time = time.time()
                                should_update = (
                                    abs(percent - progress_info['percent']) >= 5 or
                                    current_time - progress_info['last_update'] >= 30
                                )
                                
                                if should_update:
                                    # Calculate ETA
                                    elapsed = current_time - progress_info['start_time']
                                    eta_text = ""
                                    
                                    if elapsed > 60 and percent > 10:
                                        remaining_percent = 100 - percent
                                        if percent > 0:
                                            eta_seconds = (elapsed / percent) * remaining_percent
                                            eta_text = f" | ETA: {self._format_time(eta_seconds)}"
                                    
                                    # Update progress
                                    progress_info['percent'] = percent
                                    progress_info['last_update'] = current_time
                                    
                                    # Call the callback
                                    await callback(percent, current_seconds, eta_text)
                                    
                                    logger.info(f"Progress: {percent:.1f}% ({current_seconds:.1f}s/{total_duration:.1f}s){eta_text}")
                        
                        except (ValueError, IndexError, ZeroDivisionError) as e:
                            logger.debug(f"Progress parsing error: {e}")
                            continue
                    
                    # Also check for simple time format "time=00:01:30.45"
                    elif 'time=' in line:
                        try:
                            time_match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
                            if time_match:
                                hours, minutes, seconds = time_match.groups()
                                current_seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                                
                                percent = min((current_seconds / total_duration) * 100, 100)
                                
                                current_time = time.time()
                                should_update = (
                                    abs(percent - progress_info['percent']) >= 5 or
                                    current_time - progress_info['last_update'] >= 30
                                )
                                
                                if should_update:
                                    elapsed = current_time - progress_info['start_time']
                                    eta_text = ""
                                    
                                    if elapsed > 60 and percent > 10:
                                        remaining_percent = 100 - percent
                                        if percent > 0:
                                            eta_seconds = (elapsed / percent) * remaining_percent
                                            eta_text = f" | ETA: {self._format_time(eta_seconds)}"
                                    
                                    progress_info['percent'] = percent
                                    progress_info['last_update'] = current_time
                                    
                                    await callback(percent, current_seconds, eta_text)
                                    logger.info(f"Progress: {percent:.1f}% (time format){eta_text}")
                        
                        except (ValueError, IndexError, ZeroDivisionError) as e:
                            logger.debug(f"Time format parsing error: {e}")
                            continue
                
                except asyncio.TimeoutError:
                    # Send a heartbeat update every timeout period
                    current_time = time.time()
                    if current_time - progress_info['last_update'] >= 60:  # 1 minute heartbeat
                        elapsed = current_time - progress_info['start_time']
                        await callback(progress_info['percent'], 0, f" | Elapsed: {self._format_time(elapsed)}")
                        progress_info['last_update'] = current_time
                    continue
                
                except Exception as e:
                    logger.debug(f"Progress monitoring error: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"Progress monitoring failed: {e}")
    
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
                logger.info(f"Video duration detected: {self._format_time(duration)}")
                return duration
            
        except Exception as e:
            logger.error(f"Duration detection error: {e}")
        
        return None