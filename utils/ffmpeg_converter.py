import asyncio
import re
import logging
from pathlib import Path
from typing import Optional, Callable
import subprocess

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
            "-y",
            str(output_path)
        ]
        
        return await self._run_ffmpeg(cmd, progress_callback)
    
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
            "-y",
            str(output_path)
        ]
        
        return await self._run_ffmpeg(cmd, progress_callback)
    
    async def _run_ffmpeg(
        self, 
        cmd: list, 
        progress_callback: Optional[Callable] = None
    ) -> bool:
        """Execute FFmpeg command with progress tracking"""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Monitor progress if callback provided - use stdout instead of stderr
            progress_task = None
            if progress_callback:
                progress_task = asyncio.create_task(
                    self._monitor_progress(process.stdout, progress_callback)
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
            
            if process.returncode == 0:
                logger.info("FFmpeg conversion successful")
                return True
            else:
                logger.error(f"FFmpeg failed: {stderr.decode()}")
                return False
                
        except Exception as e:
            logger.error(f"FFmpeg execution error: {e}")
            return False
    
    async def _monitor_progress(
        self, 
        stream: asyncio.StreamReader,
        callback: Callable
    ):
        """Monitor FFmpeg progress output from stdout"""
        try:
            buffer = ""
            while True:
                try:
                    # Read with timeout to prevent hanging
                    data = await asyncio.wait_for(stream.read(1024), timeout=1.0)
                    if not data:
                        break
                    
                    buffer += data.decode('utf-8', errors='ignore')
                    lines = buffer.split('\n')
                    buffer = lines[-1]  # Keep incomplete line
                    
                    for line in lines[:-1]:
                        line = line.strip()
                        if line.startswith('out_time_ms='):
                            try:
                                microseconds = int(line.split('=')[1])
                                seconds = microseconds / 1000000
                                await callback(seconds)
                            except (ValueError, IndexError):
                                pass
                                
                except asyncio.TimeoutError:
                    continue  # Continue reading if no data available
                except Exception:
                    break  # Exit on any other error
                    
        except Exception as e:
            logger.debug(f"Progress monitoring stopped: {e}")
    
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
                return float(stdout.decode().strip())
            
        except Exception as e:
            logger.error(f"Duration detection error: {e}")
        
        return None