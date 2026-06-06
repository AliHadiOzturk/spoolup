#!/usr/bin/env python3
"""FFmpeg video processing module."""

import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Optional PIL import for text overlay fallback
PIL_AVAILABLE = False
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    logger.warning("Pillow not installed. Text overlay fallback will not be available.")


class TextOverlayFallback:
    """Fallback text overlay using PIL when FFmpeg drawtext is unavailable."""

    @staticmethod
    def color_to_rgb(color_str: str) -> Tuple[int, int, int]:
        """Convert color string to RGB tuple."""
        color_map = {
            "white": (255, 255, 255),
            "black": (0, 0, 0),
            "red": (255, 0, 0),
            "green": (0, 255, 0),
            "blue": (0, 0, 255),
            "yellow": (255, 255, 0),
            "cyan": (0, 255, 255),
            "magenta": (255, 0, 255),
            "orange": (255, 165, 0),
            "purple": (128, 0, 128),
            "gray": (128, 128, 128),
            "grey": (128, 128, 128),
            "pink": (255, 192, 203),
            "brown": (165, 42, 42),
        }

        color_lower = color_str.lower().strip()
        if color_lower in color_map:
            return color_map[color_lower]

        # Try hex color
        if color_str.startswith("#"):
            hex_val = color_str[1:]
            if len(hex_val) == 3:
                hex_val = "".join([c * 2 for c in hex_val])
            if len(hex_val) == 6:
                return tuple(int(hex_val[i : i + 2], 16) for i in (0, 2, 4))

        # Default to white
        return (255, 255, 255)

    @staticmethod
    def create_text_overlay_image(
        text: str,
        width: int,
        height: int,
        font_size: int = 36,
        font_color: str = "white",
        bg_color: str = "black",
        bg_opacity: float = 0.5,
        border_width: int = 0,
        border_color: str = "black",
        position_x: str = "center",
        position_y: str = "bottom",
    ) -> Optional[str]:
        """Create a transparent PNG with text overlay.

        Args:
            text: Text to render
            width: Video width
            height: Video height
            font_size: Font size in pixels
            font_color: Font color (name or hex)
            bg_color: Background color (name or hex)
            bg_opacity: Background opacity (0.0 to 1.0)
            border_width: Border width in pixels
            border_color: Border color
            position_x: Horizontal position (left, center, right)
            position_y: Vertical position (top, center, bottom)

        Returns:
            Path to temporary PNG file, or None on failure
        """
        if not PIL_AVAILABLE:
            logger.error("Pillow not available for text overlay fallback")
            return None

        try:
            # Create transparent image
            img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            # Try to load a font, fallback to default
            try:
                # Try system fonts
                font_paths = [
                    "/System/Library/Fonts/Helvetica.ttc",  # macOS
                    "/System/Library/Fonts/HelveticaNeue.ttc",  # macOS
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
                    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",  # Linux
                    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",  # Linux
                    "C:/Windows/Fonts/arial.ttf",  # Windows
                ]
                font = None
                for fp in font_paths:
                    if os.path.exists(fp):
                        font = ImageFont.truetype(fp, font_size)
                        break
                if font is None:
                    font = ImageFont.load_default()
            except Exception:
                font = ImageFont.load_default()

            # Calculate text size
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            # Calculate position
            padding = 20
            
            # Handle position_x
            try:
                x = int(float(position_x))
            except (ValueError, TypeError):
                if position_x == "left":
                    x = padding
                elif position_x == "right":
                    x = width - text_width - padding
                else:  # center
                    x = (width - text_width) // 2
            
            # Handle position_y
            try:
                y = int(float(position_y))
            except (ValueError, TypeError):
                if position_y == "top":
                    y = padding
                elif position_y == "center":
                    y = (height - text_height) // 2
                else:  # bottom
                    y = height - text_height - padding

            # Ensure text stays within bounds
            x = max(padding, min(x, width - text_width - padding))
            y = max(padding, min(y, height - text_height - padding))

            # Draw background box if opacity > 0
            if bg_opacity > 0:
                bg_rgb = TextOverlayFallback.color_to_rgb(bg_color)
                bg_rgba = (*bg_rgb, int(255 * bg_opacity))
                box_padding = 8
                draw.rectangle(
                    [
                        x - box_padding,
                        y - box_padding,
                        x + text_width + box_padding,
                        y + text_height + box_padding,
                    ],
                    fill=bg_rgba,
                )

            # Draw border if width > 0
            if border_width > 0:
                border_rgb = TextOverlayFallback.color_to_rgb(border_color)
                for offset in range(border_width):
                    for dx, dy in [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]:
                        draw.text(
                            (x + dx * (offset + 1), y + dy * (offset + 1)),
                            text,
                            font=font,
                            fill=(*border_rgb, 255),
                        )

            # Draw text
            text_rgb = TextOverlayFallback.color_to_rgb(font_color)
            draw.text((x, y), text, font=font, fill=(*text_rgb, 255))

            # Save to temp file
            temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            img.save(temp_file.name)
            temp_file.close()

            logger.info(f"Created text overlay image: {temp_file.name} ({width}x{height})")
            return temp_file.name

        except Exception as e:
            logger.exception(f"Failed to create text overlay image: {e}")
            return None


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

    def _has_drawtext_filter(self) -> bool:
        """Check if FFmpeg has the drawtext filter available."""
        try:
            result = subprocess.run(
                [self.ffmpeg_path, "-filters"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            return "drawtext" in result.stdout
        except Exception as e:
            logger.warning(f"Could not check for drawtext filter: {e}")
            return False

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

    def _parse_position(self, value: str, axis: str, dimension: int) -> str:
        """Parse position value into FFmpeg drawtext expression.

        Supports:
        - Keywords: left, center, right (x) / top, center, bottom (y)
        - Numbers: treated as pixels (e.g., "100")
        - Percentages: converted to expression (e.g., "10%" -> "w*0.1")
        - Expressions: passed through as-is (e.g., "(w-text_w)/2")

        Args:
            value: Position value string
            axis: "x" or "y"
            dimension: Video dimension in pixels (width or height)

        Returns:
            FFmpeg expression string
        """
        value = str(value).strip().lower()

        # Handle keywords
        if axis == "x":
            if value == "left":
                return "20"
            if value == "center":
                return "(w-text_w)/2"
            if value == "right":
                return "w-text_w-20"
        else:  # axis == "y"
            if value == "top":
                return "30"
            if value == "center":
                return "(h-text_h)/2"
            if value == "bottom":
                return "h-text_h-30"

        # Check if it's an expression (contains w, h, or operators)
        if any(c in value for c in ["w", "h", "(", "+", "-", "*", "/"]):
            return value

        # Check if it's a percentage
        if value.endswith("%"):
            try:
                pct = float(value[:-1]) / 100.0
                if axis == "x":
                    return f"w*{pct}"
                return f"h*{pct}"
            except ValueError:
                pass

        # Treat as raw pixel value
        try:
            float(value)
            return value
        except ValueError:
            pass

        # Fallback
        logger.warning(f"Unrecognized position value '{value}' for {axis}, using center")
        if axis == "x":
            return "(w-text_w)/2"
        return "(h-text_h)/2"

    def _evaluate_position_for_pil(self, value: str, axis: str, dimension: int) -> str:
        """Evaluate position value for PIL fallback.

        Returns a keyword or pixel value that PIL can understand.
        For expressions/percentages, approximates to center.

        Args:
            value: Position value string
            axis: "x" or "y"
            dimension: Video dimension in pixels

        Returns:
            Keyword (left, center, right, top, bottom) or pixel string
        """
        value = str(value).strip().lower()

        # Keywords pass through
        if value in ["left", "center", "right", "top", "bottom"]:
            return value

        # Check if it's a percentage
        if value.endswith("%"):
            try:
                pct = float(value[:-1]) / 100.0
                pixel = int(dimension * pct)
                return str(pixel)
            except ValueError:
                pass

        # Check if it's an expression - PIL can't handle these, fallback to center
        if any(c in value for c in ["w", "h", "(", "+", "-", "*", "/"]):
            logger.warning(f"FFmpeg expression '{value}' not supported in PIL fallback, using center")
            return "center"

        # Try to parse as number
        try:
            float(value)
            return value
        except ValueError:
            pass

        # Fallback
        return "center"

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
                - zoom_level: float, default 1.0 (1.0 = no zoom, 3.0 = max zoom, -1 = fit center with black bars)
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
        zoom_level = options.get("zoom_level", 0.1)
        crop_mode = options.get("crop_mode", "center")
        target_duration = options.get("target_duration", 60)
        speed_factor = options.get("speed_factor")
        overlay_text = options.get("add_text")
        text_overlay = options.get("text_overlay")

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
        
        if zoom_level == -1:
            # Fit Center: Scale to fit inside 9:16 frame with black bars (letterbox/pillarbox)
            logger.info("Zoom=-1: Fit center mode, maintaining aspect ratio with black bars")
            filters.append(f"scale={shorts_width}:{shorts_height}:force_original_aspect_ratio=decrease")
            filters.append(f"pad={shorts_width}:{shorts_height}:(ow-iw)/2:(oh-ih)/2:black")
        elif zoom_level == 0:
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

        # Handle text overlay
        text_overlay_image = None
        has_drawtext = self._has_drawtext_filter()

        if text_overlay or overlay_text:
            # Determine text and config
            if text_overlay:
                text = text_overlay.get("text", "")
                config = text_overlay
            else:
                text = overlay_text
                config = {
                    "text": overlay_text,
                    "position_x": "center",
                    "position_y": "bottom",
                    "text_align": "center",
                    "font_size": 36,
                    "font_color": "white",
                    "bg_color": "black",
                    "bg_opacity": 0.5,
                    "border_width": 0,
                    "border_color": "black",
                }

            if text:
                pos_x_raw = config.get("position_x", "center")
                pos_y_raw = config.get("position_y", "bottom")
                x_pos = self._parse_position(pos_x_raw, "x", shorts_width)
                y_pos = self._parse_position(pos_y_raw, "y", shorts_height)
                text_align = config.get("text_align", "center")

                if has_drawtext:
                    escaped_text = text.replace("'", "'\\''")
                    font_size = config.get("font_size", 36)
                    font_color = config.get("font_color", "white")
                    bg_color = config.get("bg_color", "black")
                    bg_opacity = config.get("bg_opacity", 0.5)
                    border_width = config.get("border_width", 0)
                    border_color = config.get("border_color", "black")

                    drawtext_parts = [
                        f"drawtext=text='{escaped_text}'",
                        f"fontsize={font_size}",
                        f"fontcolor={font_color}",
                        f"x={x_pos}",
                        f"y={y_pos}",
                    ]

                    if text_align:
                        drawtext_parts.append(f"fix_bounds=1")

                    if bg_opacity > 0:
                        drawtext_parts.extend([
                            "box=1",
                            f"boxcolor={bg_color}@{bg_opacity}",
                            "boxborderw=4",
                        ])

                    if border_width > 0:
                        drawtext_parts.extend([
                            f"borderw={border_width}",
                            f"bordercolor={border_color}",
                        ])

                    filters.append(":".join(drawtext_parts))
                    logger.info(f"Text overlay (drawtext): '{text}' at ({x_pos}, {y_pos})")
                elif PIL_AVAILABLE:
                    pil_x = self._evaluate_position_for_pil(pos_x_raw, "x", shorts_width)
                    pil_y = self._evaluate_position_for_pil(pos_y_raw, "y", shorts_height)
                    text_overlay_image = TextOverlayFallback.create_text_overlay_image(
                        text=text,
                        width=shorts_width,
                        height=shorts_height,
                        font_size=config.get("font_size", 36),
                        font_color=config.get("font_color", "white"),
                        bg_color=config.get("bg_color", "black"),
                        bg_opacity=config.get("bg_opacity", 0.5),
                        border_width=config.get("border_width", 0),
                        border_color=config.get("border_color", "black"),
                        position_x=pil_x,
                        position_y=pil_y,
                    )
                    if text_overlay_image:
                        logger.info(f"Text overlay (PIL fallback): '{text}' image created at ({pil_x}, {pil_y})")
                    else:
                        logger.error("Failed to create text overlay image")
                else:
                    logger.error("Text overlay requested but drawtext not available and Pillow not installed")

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
            # Clean up temp text overlay image if it exists
            if text_overlay_image and os.path.exists(text_overlay_image):
                os.remove(text_overlay_image)
            return False

        # Apply PIL text overlay as second pass if needed
        if text_overlay_image and os.path.exists(text_overlay_image):
            logger.info("Applying PIL text overlay as second pass")
            temp_output = output_path + ".text_overlay.mp4"
            overlay_args = [
                "-i", output_path,
                "-i", text_overlay_image,
                "-filter_complex", "[0:v][1:v]overlay=0:0:enable='between(t,0,99999)'[v]",
                "-map", "[v]",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-movflags", "+faststart",
            ]
            
            # Copy audio if present
            if has_audio:
                overlay_args.extend([
                    "-map", "0:a",
                    "-c:a", "aac",
                    "-b:a", "128k",
                ])
            else:
                overlay_args.append("-an")
            
            overlay_args.append(temp_output)
            
            overlay_success, overlay_error = self._run_ffmpeg(overlay_args)
            
            # Clean up temp text overlay image
            os.remove(text_overlay_image)
            
            if overlay_success:
                os.replace(temp_output, output_path)
                logger.info("PIL text overlay applied successfully")
            else:
                logger.error(f"PIL text overlay failed: {overlay_error}")
                if os.path.exists(temp_output):
                    os.remove(temp_output)
                # Continue with original video (no text overlay)

        logger.info(f"Video processed for shorts: {output_path}")
        return True
