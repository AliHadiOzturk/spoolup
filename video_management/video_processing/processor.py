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

        has_audio = self._has_audio_stream(input_path)
        video_speed = 1.0 / speed_factor
        audio_speed = speed_factor

        args = [
            "-i", input_path,
            "-filter_complex",
        ]

        if has_audio:
            args.append(
                f"[0:v]setpts={video_speed}*PTS[v];[0:a]atempo={audio_speed}[a]"
            )
            args.extend(["-map", "[v]", "-map", "[a]"])
        else:
            args.append(f"[0:v]setpts={video_speed}*PTS[v]")
            args.extend(["-map", "[v]"])

        args.extend([
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
        ])

        if has_audio:
            args.extend(["-c:a", "aac", "-b:a", "128k"])
        else:
            args.append("-an")

        args.append(output_path)

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

    def _has_audio_stream(self, input_path: str) -> bool:
        """Check if video file has an audio stream."""
        cmd = [
            self.ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
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
                return False
            data = json.loads(result.stdout)
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "audio":
                    return True
            return False
        except Exception:
            return False

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
                - zoom_level: float, default 1.0 (1.0 = no zoom, 3.0 = max zoom)
                - crop_mode: 'center' (default), 'left', 'right', 'smart'
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
        zoom_level = options.get("zoom_level", 1.0)
        crop_mode = options.get("crop_mode", "center")
        target_duration = options.get("target_duration", 60)
        speed_factor = options.get("speed_factor")
        overlay_text = options.get("add_text")

        info = self.get_video_info(input_path)
        if not info:
            logger.error("Failed to get video info")
            return False

        # Check if video has audio
        has_audio = self._has_audio_stream(input_path)
        logger.info(f"Video has audio: {has_audio}")

        duration = info["duration"]
        width = info["width"]
        height = info["height"]

        if duration > target_duration:
            logger.info(f"Video duration {duration}s exceeds target {target_duration}s, will trim")

        filters = []

        # Calculate crop for 9:16 aspect ratio
        target_aspect = 9.0 / 16.0
        current_aspect = width / height
        
        logger.info(
            f"Processing with zoom={zoom_level}, crop_mode={crop_mode}, "
            f"input={width}x{height}, target_aspect={target_aspect:.3f}"
        )

        # Standard output resolution for YouTube Shorts
        shorts_width = 1080
        shorts_height = 1920
        
        if zoom_level == 0:
            # Zoom 0: Standard 9:16 conversion, fill the entire frame (no extra zoom)
            logger.info("Zoom=0: Standard 9:16 conversion, filling frame")
            if current_aspect > target_aspect:
                # Video is wider than 9:16, crop sides to fill frame
                target_width = int(height * target_aspect)
                x_offset = (width - target_width) // 2
                filters.append(f"crop={target_width}:{height}:{x_offset}:0")
                filters.append(f"scale={shorts_width}:{shorts_height}")
            else:
                # Already 9:16 or taller, just scale
                filters.append(f"scale={shorts_width}:{shorts_height}")
        elif current_aspect > target_aspect:
            # Video is wider than 9:16 (e.g., 16:9), crop the sides based on zoom
            target_width = height * target_aspect
            crop_width = target_width / zoom_level

            # Clamp crop_width
            max_crop_width = float(width)
            min_crop_width = target_width / 3.0
            crop_width = max(min_crop_width, min(crop_width, max_crop_width))
            crop_width_int = int(crop_width)

            # Determine x_offset based on crop_mode
            if crop_mode == "left":
                x_offset = 0
            elif crop_mode == "right":
                x_offset = width - crop_width_int
            elif crop_mode in ("center", "smart"):
                x_offset = (width - crop_width_int) / 2
            else:
                x_offset = (width - crop_width_int) / 2

            logger.info(f"Cropping {width}x{height} to {crop_width_int}x{height} (offset: {x_offset}, zoom: {zoom_level})")
            filters.append(f"crop={crop_width_int}:{height}:{int(x_offset)}:0")
            filters.append(f"scale={shorts_width}:{shorts_height}")
        else:
            # Video is already 9:16 or taller, just scale to standard resolution
            logger.info(f"Scaling {width}x{height} to {shorts_width}x{shorts_height}")
            filters.append(f"scale={shorts_width}:{shorts_height}")

        # Add text overlay if specified
        if overlay_text:
            escaped_text = overlay_text.replace("'", "'\\''")
            filters.append(
                f"drawtext=text='{escaped_text}':"
                f"fontsize=36:fontcolor=white:"
                f"box=1:boxcolor=black@0.5:"
                f"x=(w-text_w)/2:y=h-text_h-30"
            )

        # Log the filter chain for debugging
        logger.info(f"Filter chain: {filters}")
        
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

            if has_audio:
                # Adjust both video and audio speed
                args.extend([
                    "-filter_complex",
                    f"[0:v]{','.join(filters)}[v];[0:a]atempo={speed_factor}[a]",
                    "-map", "[v]",
                    "-map", "[a]",
                ])
            else:
                # No audio stream, only process video
                args.extend([
                    "-filter_complex",
                    f"[0:v]{','.join(filters)}[v]",
                    "-map", "[v]",
                ])
        elif filters:
            args.extend(["-vf", ",".join(filters)])

        # Encoding settings
        args.extend([
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
        ])

        # Only add audio codec if video has audio
        if has_audio:
            args.extend([
                "-c:a", "aac",
                "-b:a", "128k",
            ])
        else:
            args.append("-an")

        args.extend([
            "-movflags", "+faststart",
            output_path,
        ])

        success, error = self._run_ffmpeg(args)
        if not success:
            logger.error(f"Process for shorts failed: {error}")
            return False

        logger.info(f"Video processed for shorts: {output_path}")
        return True
