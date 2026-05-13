#!/usr/bin/env python3
"""FFmpeg video processing module."""

import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class VideoProcessor:
    """Video processing using FFmpeg."""

    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"):
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self._validate_ffmpeg()

    def _validate_ffmpeg(self) -> None:
        """Validate ffmpeg is available on the system."""
        try:
            subprocess.run(
                [self.ffmpeg_path, "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            logger.info(f"FFmpeg found: {self.ffmpeg_path}")
        except FileNotFoundError:
            logger.error(f"FFmpeg not found at: {self.ffmpeg_path}")
            raise RuntimeError(
                f"FFmpeg not found at '{self.ffmpeg_path}'. "
                "Please install FFmpeg or provide the correct path."
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg validation failed: {e}")
            raise RuntimeError(f"FFmpeg validation failed: {e}")

        try:
            subprocess.run(
                [self.ffprobe_path, "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            logger.info(f"FFprobe found: {self.ffprobe_path}")
        except FileNotFoundError:
            logger.error(f"FFprobe not found at: {self.ffprobe_path}")
            raise RuntimeError(
                f"FFprobe not found at '{self.ffprobe_path}'. "
                "Please install FFmpeg or provide the correct path."
            )

    def _run_ffmpeg(self, args: List[str]) -> Tuple[bool, str]:
        """Run ffmpeg with given arguments."""
        cmd = [self.ffmpeg_path, "-y"] + args
        logger.info(f"Running FFmpeg command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                logger.error(f"FFmpeg failed with code {result.returncode}: {result.stderr}")
                return False, result.stderr

            logger.info("FFmpeg command completed successfully")
            return True, result.stdout

        except Exception as e:
            logger.exception(f"FFmpeg execution failed: {e}")
            return False, str(e)

    def get_video_info(self, input_path: str) -> Optional[Dict[str, Any]]:
        """Get video metadata using ffprobe.

        Args:
            input_path: Path to input video file

        Returns:
            Dictionary with duration, width, height, fps, and other metadata
        """
        if not os.path.exists(input_path):
            logger.error(f"Input file not found: {input_path}")
            return None

        cmd = [
            self.ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            input_path,
        ]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                logger.error(f"FFprobe failed with return code {result.returncode}")
                logger.error(f"FFprobe command: {' '.join(cmd)}")
                logger.error(f"FFprobe stderr: {result.stderr}")
                logger.error(f"FFprobe stdout: {result.stdout[:500]}")
                return None

            data = json.loads(result.stdout)

            video_stream = None
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    video_stream = stream
                    break

            if not video_stream:
                logger.error("No video stream found")
                return None

            width = int(video_stream.get("width", 0))
            height = int(video_stream.get("height", 0))

            duration = 0.0
            if "duration" in video_stream:
                duration = float(video_stream["duration"])
            elif "duration" in data.get("format", {}):
                duration = float(data["format"]["duration"])

            fps = 0.0
            r_frame_rate = video_stream.get("r_frame_rate", "")
            if "/" in r_frame_rate:
                num, den = r_frame_rate.split("/")
                fps = float(num) / float(den)

            info = {
                "duration": duration,
                "width": width,
                "height": height,
                "fps": fps,
                "bitrate": int(data.get("format", {}).get("bit_rate", 0)),
                "codec": video_stream.get("codec_name", ""),
                "pixel_format": video_stream.get("pix_fmt", ""),
            }

            logger.info(f"Video info for {input_path}: {info}")
            return info

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse FFprobe output: {e}")
            return None
        except (ValueError, KeyError) as e:
            logger.error(f"Failed to parse video metadata: {e}")
            return None
        except Exception as e:
            logger.exception(f"FFprobe execution failed: {e}")
            return None

    def trim_video(
        self,
        input_path: str,
        output_path: str,
        start_time: float,
        duration: float,
    ) -> bool:
        """Trim video to specified duration.

        Args:
            input_path: Path to input video file
            output_path: Path to output video file
            start_time: Start time in seconds
            duration: Duration in seconds

        Returns:
            True if successful, False otherwise
        """
        if not os.path.exists(input_path):
            logger.error(f"Input file not found: {input_path}")
            return False

        args = [
            "-ss", str(start_time),
            "-t", str(duration),
            "-i", input_path,
            "-c", "copy",
            output_path,
        ]

        success, error = self._run_ffmpeg(args)
        if not success:
            logger.error(f"Trim video failed: {error}")
            return False

        logger.info(f"Video trimmed: {output_path}")
        return True

    def speed_up(
        self,
        input_path: str,
        output_path: str,
        speed_factor: float,
    ) -> bool:
        """Speed up video playback.

        Args:
            input_path: Path to input video file
            output_path: Path to output video file
            speed_factor: Speed multiplier (e.g., 2.0 for 2x speed)

        Returns:
            True if successful, False otherwise
        """
        if not os.path.exists(input_path):
            logger.error(f"Input file not found: {input_path}")
            return False

        if speed_factor <= 0:
            logger.error(f"Invalid speed factor: {speed_factor}")
            return False

        video_speed = 1.0 / speed_factor
        audio_speed = speed_factor

        args = [
            "-i", input_path,
            "-filter_complex",
            f"[0:v]setpts={video_speed}*PTS[v];[0:a]atempo={audio_speed}[a]",
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            output_path,
        ]

        success, error = self._run_ffmpeg(args)
        if not success:
            logger.error(f"Speed up video failed: {error}")
            return False

        logger.info(f"Video sped up by {speed_factor}x: {output_path}")
        return True

    def add_text_overlay(
        self,
        input_path: str,
        output_path: str,
        text: str,
        position: str = "bottom",
    ) -> bool:
        """Add text overlay to video.

        Args:
            input_path: Path to input video file
            output_path: Path to output video file
            text: Text to overlay
            position: Position of text (top, bottom, center)

        Returns:
            True if successful, False otherwise
        """
        if not os.path.exists(input_path):
            logger.error(f"Input file not found: {input_path}")
            return False

        escaped_text = text.replace("'", "'\\''")

        if position == "top":
            y_position = "20"
        elif position == "center":
            y_position = "(h-text_h)/2"
        else:  # bottom
            y_position = "h-text_h-20"

        drawtext_filter = (
            f"drawtext=text='{escaped_text}':"
            f"fontsize=48:fontcolor=white:"
            f"box=1:boxcolor=black@0.5:"
            f"x=(w-text_w)/2:y={y_position}"
        )

        args = [
            "-i", input_path,
            "-vf", drawtext_filter,
            "-c:a", "copy",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            output_path,
        ]

        success, error = self._run_ffmpeg(args)
        if not success:
            logger.error(f"Add text overlay failed: {error}")
            return False

        logger.info(f"Text overlay added: {output_path}")
        return True

    def create_thumbnail(
        self,
        input_path: str,
        output_path: str,
        time_position: float = 0.0,
    ) -> bool:
        """Create thumbnail from video frame.

        Args:
            input_path: Path to input video file
            output_path: Path to output thumbnail file
            time_position: Time position in seconds for the frame

        Returns:
            True if successful, False otherwise
        """
        if not os.path.exists(input_path):
            logger.error(f"Input file not found: {input_path}")
            return False

        args = [
            "-ss", str(time_position),
            "-i", input_path,
            "-vframes", "1",
            "-q:v", "2",
            output_path,
        ]

        success, error = self._run_ffmpeg(args)
        if not success:
            logger.error(f"Create thumbnail failed: {error}")
            return False

        logger.info(f"Thumbnail created: {output_path}")
        return True

    def process_for_shorts(
        self,
        input_path: str,
        output_path: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Convert 16:9 video to 9:16 format for YouTube Shorts/TikTok.

        Args:
            input_path: Path to input video file
            output_path: Path to output video file
            options: Processing options dict with keys:
                - crop_mode: 'center' (default), 'smart', 'split'
                - target_duration: max seconds (default 60)
                - speed_factor: playback speed multiplier
                - add_text: overlay text

        Returns:
            True if successful, False otherwise
        """
        if not os.path.exists(input_path):
            logger.error(f"Input file not found: {input_path}")
            return False

        options = options or {}
        crop_mode = options.get("crop_mode", "center")
        target_duration = options.get("target_duration", 60)
        speed_factor = options.get("speed_factor")
        overlay_text = options.get("add_text")

        info = self.get_video_info(input_path)
        if not info:
            logger.error("Failed to get video info")
            return False

        duration = info["duration"]
        width = info["width"]
        height = info["height"]

        if duration > target_duration:
            logger.info(f"Video duration {duration}s exceeds target {target_duration}s, will trim")

        filters = []

        # Calculate crop for 9:16 aspect ratio
        target_aspect = 9.0 / 16.0
        current_aspect = width / height

        if current_aspect > target_aspect:
            # Video is wider than target, crop width
            new_width = int(height * target_aspect)
            if crop_mode == "center":
                x_offset = (width - new_width) // 2
                filters.append(f"crop={new_width}:{height}:{x_offset}:0")
            elif crop_mode == "smart":
                # Smart crop - keep left portion for now
                filters.append(f"crop={new_width}:{height}:0:0")
            elif crop_mode == "split":
                # Split screen - duplicate and stack side by side
                filters.append(f"scale={width}:{height // 2}")
                filters.append(f"tile=1x2")
            else:
                x_offset = (width - new_width) // 2
                filters.append(f"crop={new_width}:{height}:{x_offset}:0")
        else:
            # Video is taller than target, pad or scale
            new_height = int(width / target_aspect)
            if new_height > height:
                # Need to pad
                y_offset = (new_height - height) // 2
                filters.append(f"pad={width}:{new_height}:0:{y_offset}:black")
            else:
                # Scale to fit
                filters.append(f"scale={width}:{new_height}")

        # Add text overlay if specified
        if overlay_text:
            escaped_text = overlay_text.replace("'", "'\\''")
            filters.append(
                f"drawtext=text='{escaped_text}':"
                f"fontsize=36:fontcolor=white:"
                f"box=1:boxcolor=black@0.5:"
                f"x=(w-text_w)/2:y=h-text_h-30"
            )

        # Build ffmpeg command
        args = ["-i", input_path]

        # Add trim if needed
        if duration > target_duration:
            args.extend(["-t", str(target_duration)])

        # Add speed filter if specified
        if speed_factor and speed_factor > 0:
            speed_filter = f"setpts=PTS/{speed_factor}"
            if filters:
                filters.insert(0, speed_filter)
            else:
                filters.append(speed_filter)

            # Adjust audio speed
            args.extend([
                "-filter_complex",
                f"[0:v]{','.join(filters)}[v];[0:a]atempo={speed_factor}[a]",
                "-map", "[v]",
                "-map", "[a]",
            ])
        elif filters:
            args.extend(["-vf", ",".join(filters)])

        # Encoding settings
        args.extend([
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            output_path,
        ])

        success, error = self._run_ffmpeg(args)
        if not success:
            logger.error(f"Process for shorts failed: {error}")
            return False

        logger.info(f"Video processed for shorts: {output_path}")
        return True
