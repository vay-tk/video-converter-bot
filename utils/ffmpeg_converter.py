import asyncio
import re
import logging
import time
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)

class FFmpegConverter:
    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path
    
    async def convert_to_mp4(
        self, 
        input_path: Path, 
        output_path: Path,
        progress_callback: Optional[Callable] = None
    ) -> bool:
        """Convert video to MP4 (H.264 + AAC)"""
        logger.info("FFMPEG CONVERTER: Starting MP4 conversion")
        
        # Get duration first
        duration = await self.get_video_duration(input_path)
        logger.info(f"VIDEO DURATION: {duration} seconds")
        
        cmd = [
            self.ffmpeg_path,
            "-i", str(input_path),
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "slow",
            "-crf", "23",
            "-map", "0:v:0",
            "-map", "0:a:0?",
            "-map", "0:s:0?",
            "-movflags", "+faststart",
            "-progress", "pipe:2",
            "-nostats",
            "-loglevel", "error",
            "-y",
            str(output_path)
        ]
        
        return await self._run_ffmpeg_with_progress(cmd, progress_callback, duration)
    
    async def convert_to_mkv(
        self,
        input_path: Path,
        output_path: Path,
        progress_callback: Optional[Callable] = None
    ) -> bool:
        """Convert video to MKV (H.265 + AAC, 480p, CRF 28)"""
        logger.info("FFMPEG CONVERTER: Starting MKV conversion")
        
        # Get duration first
        duration = await self.get_video_duration(input_path)
        logger.info(f"VIDEO DURATION: {duration} seconds")
        
        cmd = [
            self.ffmpeg_path,
            "-i", str(input_path),
            "-c:v", "libx265",
            "-crf", "30",
            "-preset", "slow",
            "-vf", "scale=-2:480",
            "-c:a", "libopus",
            "-b:a", "56k",
            "-map", "0:v:0",
            "-map", "0:a",
            "-map", "0:s?",
            "-progress", "pipe:2",
            "-nostats",
            "-loglevel", "error",
            "-y",
            str(output_path)
        ]
        
        return await self._run_ffmpeg_with_progress(cmd, progress_callback, duration)
    
    async def _run_ffmpeg_with_progress(
        self, 
        cmd: list, 
        progress_callback: Optional[Callable],
        duration: Optional[float]
    ) -> bool:
        """Run FFmpeg with working progress tracking"""
        try:
            logger.info(f"EXECUTING COMMAND: {' '.join(cmd[:5])}...")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Track progress if callback and duration available
            progress_task = None
            if progress_callback and duration:
                logger.info("STARTING PROGRESS MONITORING")
                progress_task = asyncio.create_task(
                    self._monitor_ffmpeg_progress(process.stderr, progress_callback, duration)
                )
            else:
                logger.warning(f"NO PROGRESS TRACKING: callback={bool(progress_callback)}, duration={duration}")
            
            # Wait for completion
            stdout, stderr = await process.communicate()
            
            # Stop progress monitoring
            if progress_task:
                progress_task.cancel()
                try:
                    await progress_task
                except asyncio.CancelledError:
                    pass
            
            # Check result
            if process.returncode == 0:
                logger.info("FFMPEG SUCCESS")
                return True
            else:
                logger.error(f"FFMPEG FAILED: {stderr.decode()}")
                return False
                
        except Exception as e:
            logger.error(f"FFMPEG EXECUTION ERROR: {e}")
            return False
    
    async def _monitor_ffmpeg_progress(
        self,
        stderr_stream: asyncio.StreamReader,
        callback: Callable,
        total_duration: float
    ):
        """Monitor FFmpeg progress - SIMPLIFIED VERSION THAT WORKS"""
        try:
            logger.info("PROGRESS MONITOR STARTED")
            last_percent = 0
            start_time = time.time()
            
            while True:
                try:
                    # Read line with timeout
                    line = await asyncio.wait_for(stderr_stream.readline(), timeout=5.0)
                    if not line:
                        logger.info("PROGRESS MONITOR: EOF reached")
                        break
                    
                    line_str = line.decode('utf-8', errors='ignore').strip()
                    
                    # Parse progress from different possible formats
                    current_seconds = None
                    
                    # Format 1: out_time_us=123456789
                    if 'out_time_us=' in line_str:
                        match = re.search(r'out_time_us=(\d+)', line_str)
                        if match:
                            microseconds = int(match.group(1))
                            current_seconds = microseconds / 1000000
                    
                    # Format 2: out_time_ms=123456
                    elif 'out_time_ms=' in line_str:
                        match = re.search(r'out_time_ms=(\d+)', line_str)
                        if match:
                            milliseconds = int(match.group(1))
                            current_seconds = milliseconds / 1000
                    
                    # Format 3: time=00:01:30.45
                    elif 'time=' in line_str:
                        match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line_str)
                        if match:
                            hours, minutes, seconds = match.groups()
                            current_seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                    
                    # If we found a time, calculate progress
                    if current_seconds is not None and current_seconds > 0:
                        percent = min((current_seconds / total_duration) * 100, 100)
                        
                        # Update every 5% or every 30 seconds
                        elapsed = time.time() - start_time
                        if percent - last_percent >= 5 or elapsed >= 30:
                            # Calculate ETA
                            eta_text = ""
                            if elapsed > 60 and percent > 5:
                                remaining = (100 - percent) * (elapsed / percent)
                                eta_text = f" | ETA: {self._format_time(remaining)}"
                            
                            logger.info(f"PROGRESS UPDATE: {percent:.1f}% ({current_seconds:.1f}s/{total_duration:.1f}s){eta_text}")
                            
                            # Call the callback
                            try:
                                await callback(percent, current_seconds, eta_text)
                                last_percent = percent
                                start_time = time.time()  # Reset timer after update
                            except Exception as e:
                                logger.error(f"CALLBACK ERROR: {e}")
                
                except asyncio.TimeoutError:
                    # Send heartbeat every 30 seconds if no progress
                    elapsed = time.time() - start_time
                    if elapsed >= 30:
                        logger.info("PROGRESS HEARTBEAT")
                        try:
                            await callback(last_percent, 0, f" | Processing... ({self._format_time(elapsed)})")
                            start_time = time.time()
                        except Exception as e:
                            logger.error(f"HEARTBEAT CALLBACK ERROR: {e}")
                    continue
                
                except Exception as e:
                    logger.error(f"PROGRESS MONITOR ERROR: {e}")
                    break
            
            logger.info("PROGRESS MONITOR FINISHED")
            
        except Exception as e:
            logger.error(f"PROGRESS MONITORING FAILED: {e}")
    
    def _format_time(self, seconds: float) -> str:
        """Format seconds into readable time"""
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
                logger.info(f"DURATION DETECTED: {duration} seconds ({self._format_time(duration)})")
                return duration
            else:
                logger.error("DURATION DETECTION FAILED")
            
        except Exception as e:
            logger.error(f"DURATION ERROR: {e}")
        
        return None
