#!/usr/bin/env python3
"""Text overlay module for post-processing."""

import logging
import os
import subprocess
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class TextOverlayManager:
    """Manage text overlays on videos using FFmpeg drawtext filter."""

    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path
        self._validate_ffmpeg()

    def _validate_ffmpeg(self) -> None:
        """Validate ffmpeg is available."""
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

    def validate_overlays(self, overlays: List[Dict[str, Any]]) -> bool:
        """Validate overlay configurations.

        Args:
            overlays: List of overlay dictionaries

        Returns:
            True if valid, False otherwise
        """
        if not overlays:
            logger.warning("No overlays provided")
            return False

        required_fields = ["text", "position_x", "position_y"]

        for i, overlay in enumerate(overlays):
            for field in required_fields:
                if field not in overlay:
                    logger.error(f"Overlay {i} missing required field: {field}")
                    return False

            if not overlay.get("text"):
                logger.error(f"Overlay {i} has empty text")
                return False

            # Validate numeric fields
            numeric_fields = ["position_x", "position_y", "font_size", "start_time", "end_time"]
            for field in numeric_fields:
                if field in overlay:
                    try:
                        float(overlay[field])
                    except (ValueError, TypeError):
                        logger.error(f"Overlay {i} has invalid {field}: {overlay[field]}")
                        return False

            # Validate time range
            if "start_time" in overlay and "end_time" in overlay:
                start = float(overlay["start_time"])
                end = float(overlay["end_time"])
                if start >= end:
                    logger.error(f"Overlay {i} has invalid time range: {start} >= {end}")
                    return False

        logger.info(f"Validated {len(overlays)} overlays")
        return True

    def _escape_text(self, text: str) -> str:
        """Escape text for FFmpeg drawtext filter."""
        return text.replace("'", "'\\''").replace(":", "\\:")

    def _build_drawtext_filter(self, overlay: Dict[str, Any]) -> str:
        """Build a single drawtext filter string.

        Args:
            overlay: Overlay configuration dictionary

        Returns:
            FFmpeg drawtext filter string
        """
        text = self._escape_text(str(overlay["text"]))
        position_x = str(overlay["position_x"])
        position_y = str(overlay["position_y"])
        font_size = str(overlay.get("font_size", 48))
        font_color = str(overlay.get("font_color", "white"))
        bg_color = overlay.get("bg_color")

        filter_parts = [
            f"drawtext=text='{text}'",
            f"fontsize={font_size}",
            f"fontcolor={font_color}",
            f"x={position_x}",
            f"y={position_y}",
        ]

        if bg_color:
            filter_parts.extend([
                "box=1",
                f"boxcolor={bg_color}",
            ])

        # Add time enable filter if start/end times are specified
        if "start_time" in overlay and "end_time" in overlay:
            start_time = float(overlay["start_time"])
            end_time = float(overlay["end_time"])
            filter_parts.append(f"enable='between(t\\,{start_time}\\,{end_time})'")

        return ":".join(filter_parts)

    def apply_overlays(
        self,
        video_path: str,
        output_path: str,
        overlays: List[Dict[str, Any]],
    ) -> bool:
        """Apply text overlays to video.

        Args:
            video_path: Path to input video file
            output_path: Path to output video file
            overlays: List of overlay dictionaries with keys:
                - text: Text to display
                - position_x: X position (can be expression like "20" or "(w-text_w)/2")
                - position_y: Y position (can be expression like "20" or "h-text_h-20")
                - font_size: Font size in pixels (default: 48)
                - font_color: Font color (default: "white")
                - bg_color: Background color (optional)
                - start_time: Start time in seconds (optional)
                - end_time: End time in seconds (optional)

        Returns:
            True if successful, False otherwise
        """
        if not os.path.exists(video_path):
            logger.error(f"Video file not found: {video_path}")
            return False

        if not self.validate_overlays(overlays):
            return False

        try:
            # Build drawtext filters for all overlays
            filters = []
            for overlay in overlays:
                drawtext = self._build_drawtext_filter(overlay)
                filters.append(drawtext)

            # Combine filters
            filter_string = ",".join(filters)

            args = [
                "-i", video_path,
                "-vf", filter_string,
                "-c:a", "copy",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                output_path,
            ]

            success, error = self._run_ffmpeg(args)
            if not success:
                logger.error(f"Apply overlays failed: {error}")
                return False

            logger.info(f"Overlays applied successfully: {output_path}")
            return True

        except Exception as e:
            logger.exception(f"Apply overlays failed: {e}")
            return False
