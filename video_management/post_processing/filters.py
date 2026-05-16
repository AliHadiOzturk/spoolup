#!/usr/bin/env python3
"""Video filters module for post-processing."""

import logging
import os
import subprocess
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class VideoFilter:
    """Apply video filters using FFmpeg."""

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

    def apply_filter(
        self,
        video_path: str,
        output_path: str,
        filter_name: str,
        **params: Any,
    ) -> bool:
        """Apply a video filter.

        Args:
            video_path: Path to input video file
            output_path: Path to output video file
            filter_name: Name of the filter to apply
            **params: Filter-specific parameters

        Supported filters:
            - "brightness": Adjust brightness and contrast
                params: brightness (-1.0 to 1.0), contrast (0.0 to 2.0)
            - "saturation": Adjust saturation
                params: saturation (0.0 to 3.0)
            - "blackwhite": Convert to black and white
                params: none
            - "sepia": Apply sepia tone
                params: none
            - "vintage": Apply vintage effect (sepia + contrast + brightness)
                params: none
            - "speed": Change playback speed
                params: speed_factor (float)

        Returns:
            True if successful, False otherwise
        """
        if not os.path.exists(video_path):
            logger.error(f"Video file not found: {video_path}")
            return False

        try:
            filter_string = self._build_filter_string(filter_name, **params)
            if not filter_string:
                logger.error(f"Failed to build filter string for: {filter_name}")
                return False

            # Handle speed filter separately as it requires audio adjustment
            if filter_name == "speed":
                return self._apply_speed_filter(video_path, output_path, **params)

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
                logger.error(f"Apply filter failed: {error}")
                return False

            logger.info(f"Filter '{filter_name}' applied successfully: {output_path}")
            return True

        except Exception as e:
            logger.exception(f"Apply filter failed: {e}")
            return False

    def _build_filter_string(self, filter_name: str, **params: Any) -> Optional[str]:
        """Build FFmpeg filter string for the given filter.

        Args:
            filter_name: Name of the filter
            **params: Filter parameters

        Returns:
            FFmpeg filter string or None if filter not supported
        """
        if filter_name == "brightness":
            brightness = float(params.get("brightness", 0.0))
            contrast = float(params.get("contrast", 1.0))

            # Clamp values
            brightness = max(-1.0, min(1.0, brightness))
            contrast = max(0.0, min(2.0, contrast))

            return f"eq=brightness={brightness}:contrast={contrast}"

        elif filter_name == "saturation":
            saturation = float(params.get("saturation", 1.0))

            # Clamp value
            saturation = max(0.0, min(3.0, saturation))

            return f"eq=saturation={saturation}"

        elif filter_name == "blackwhite":
            # Use colorchannelmixer for better B&W conversion
            return "colorchannelmixer=.3:.4:.3:0:.3:.4:.3:0:.3:.4:.3"

        elif filter_name == "sepia":
            return "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131"

        elif filter_name == "vintage":
            # Combine sepia with contrast and brightness adjustments
            sepia = "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131"
            brightness_contrast = "eq=brightness=0.1:contrast=1.2"
            return f"{sepia},{brightness_contrast}"

        elif filter_name == "speed":
            # Speed filter is handled separately in _apply_speed_filter
            return ""

        else:
            logger.error(f"Unknown filter: {filter_name}")
            return None

    def _apply_speed_filter(self, video_path: str, output_path: str, **params: Any) -> bool:
        """Apply speed filter with audio adjustment.

        Args:
            video_path: Path to input video file
            output_path: Path to output video file
            **params: Filter parameters

        Returns:
            True if successful, False otherwise
        """
        speed_factor = float(params.get("speed_factor", 1.0))

        if speed_factor <= 0:
            logger.error(f"Invalid speed factor: {speed_factor}")
            return False

        video_speed = 1.0 / speed_factor
        audio_speed = speed_factor

        # Limit audio speed to atempo valid range (0.5 to 2.0)
        # For speeds outside this range, we need to chain atempo filters
        atempo_filters = []
        remaining_speed = audio_speed

        while remaining_speed > 2.0:
            atempo_filters.append("atempo=2.0")
            remaining_speed /= 2.0

        while remaining_speed < 0.5:
            atempo_filters.append("atempo=0.5")
            remaining_speed /= 0.5

        atempo_filters.append(f"atempo={remaining_speed}")
        atempo_string = ",".join(atempo_filters)

        args = [
            "-i", video_path,
            "-filter_complex",
            f"[0:v]setpts={video_speed}*PTS[v];[0:a]{atempo_string}[a]",
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
            logger.error(f"Apply speed filter failed: {error}")
            return False

        logger.info(f"Speed filter applied ({speed_factor}x): {output_path}")
        return True
