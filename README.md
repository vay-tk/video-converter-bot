# c:\Users\vm\Desktop\video converter bot\README.md
# Telegram Video Converter Bot

A robust production-grade Telegram bot for converting video files using FFmpeg.

## Features

- **Multiple Formats**: Convert to MP4 (H.264) or MKV (H.265)
- **Large Files**: Handle files up to 2GB
- **Progress Tracking**: Real-time conversion progress
- **Audio/Subtitle Preservation**: Maintains all tracks
- **Auto Cleanup**: Temporary file management
- **Error Handling**: Comprehensive error management

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Install FFmpeg**:
   - Windows: Download from https://ffmpeg.org/
   - Linux: `sudo apt install ffmpeg`
   - macOS: `brew install ffmpeg`

3. **Configure Bot**:
   - Copy `.env.example` to `.env`
   - Fill in your Telegram Bot credentials
   - Get API_ID and API_HASH from https://my.telegram.org/
   - Get BOT_TOKEN from @BotFather

4. **Run Bot**:
   ```bash
   python run.py
   ```

## Configuration

- `MAX_FILE_SIZE`: Maximum file size (default: 2GB)
- `TEMP_DIR`: Temporary storage directory
- `FFMPEG_PATH`: FFmpeg executable path

## Conversion Options

### MP4 Format
- Video: H.264 codec
- Audio: AAC codec
- Preserves: Default audio and subtitle tracks
- Quality: CRF 23 (high quality)

### MKV Format
- Video: H.265 codec, CRF 28, 480p resolution
- Audio: AAC codec, 96k bitrate
- Preserves: All audio and subtitle tracks
- Size: Optimized for smaller file size

## Production Deployment

1. Use process manager (PM2, systemd)
2. Configure logging rotation
3. Set up monitoring
4. Use environment-specific configurations
5. Implement health checks

## Error Handling

- File size validation
- Download/upload progress tracking
- FFmpeg process monitoring
- Automatic cleanup on failure
- User-friendly error messages