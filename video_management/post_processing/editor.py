#!/usr/bin/env python3
"""Post-processing editor module for video management."""

import json
import logging
import os
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from post_processing.audio_mixer import AudioMixer
from post_processing.text_overlay import TextOverlayManager
from post_processing.filters import VideoFilter

logger = logging.getLogger(__name__)


class PostProcessor:
    """Main orchestrator for video post-processing operations."""

    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"):
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.audio_mixer = AudioMixer(ffmpeg_path, ffprobe_path)
        self.text_overlay = TextOverlayManager(ffmpeg_path)
        self.video_filter = VideoFilter(ffmpeg_path)
        self._validate_tools()

    def _validate_tools(self) -> None:
        """Validate ffmpeg and ffprobe are available."""
        for tool_path, tool_name in [(self.ffmpeg_path, "FFmpeg"), (self.ffprobe_path, "FFprobe")]:
            try:
                subprocess.run(
                    [tool_path, "-version"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                )
                logger.info(f"{tool_name} found: {tool_path}")
            except FileNotFoundError:
                logger.error(f"{tool_name} not found at: {tool_path}")
                raise RuntimeError(
                    f"{tool_name} not found at '{tool_path}'. "
                    "Please install FFmpeg or provide the correct path."
                )
            except subprocess.CalledProcessError as e:
                logger.error(f"{tool_name} validation failed: {e}")
                raise RuntimeError(f"{tool_name} validation failed: {e}")

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

    def get_video_info(self, video_path: str) -> Optional[Dict[str, Any]]:
        """Get video metadata using ffprobe.

        Args:
            video_path: Path to input video file

        Returns:
            Dictionary with duration, width, height, fps, and other metadata
        """
        if not os.path.exists(video_path):
            logger.error(f"Video file not found: {video_path}")
            return None

        cmd = [
            self.ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            video_path,
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
                logger.error(f"FFprobe stderr: {result.stderr}")
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

            logger.info(f"Video info for {video_path}: {info}")
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

    def validate_operations(self, operations: List[Dict[str, Any]]) -> bool:
        """Validate post-processing operations.

        Args:
            operations: List of operation dictionaries

        Returns:
            True if valid, False otherwise
        """
        if not operations:
            logger.warning("No operations provided")
            return False

        valid_types = {"audio", "text", "filter"}

        for i, operation in enumerate(operations):
            if "type" not in operation:
                logger.error(f"Operation {i} missing required field: type")
                return False

            op_type = operation["type"]
            if op_type not in valid_types:
                logger.error(f"Operation {i} has invalid type: {op_type}")
                return False

            if op_type == "audio":
                if "audio_path" not in operation:
                    logger.error(f"Operation {i} (audio) missing audio_path")
                    return False

            elif op_type == "text":
                if "overlays" not in operation:
                    logger.error(f"Operation {i} (text) missing overlays")
                    return False

            elif op_type == "filter":
                if "filter_name" not in operation:
                    logger.error(f"Operation {i} (filter) missing filter_name")
                    return False

        logger.info(f"Validated {len(operations)} operations")
        return True

    def process(
        self,
        processed_video_id: str,
        operations: List[Dict[str, Any]],
        video_path: str,
        output_path: Optional[str] = None,
    ) -> bool:
        """Process video with a chain of operations.

        Args:
            processed_video_id: ID of the processed video
            operations: List of operation dictionaries with keys:
                - type: "audio", "text", or "filter"
                - For audio: audio_path, volume, fade_in, fade_out
                - For text: overlays (list of overlay dicts)
                - For filter: filter_name, **params
            video_path: Path to input video file
            output_path: Path to output video file (defaults to overwriting input)

        Returns:
            True if successful, False otherwise
        """
        if not os.path.exists(video_path):
            logger.error(f"Video file not found: {video_path}")
            return False

        if not self.validate_operations(operations):
            return False

        # Use input path as output if not specified
        if output_path is None:
            output_path = video_path

        # Create temporary directory for intermediate files
        temp_dir = tempfile.mkdtemp(prefix=f"post_process_{processed_video_id}_")
        current_path = video_path

        try:
            for i, operation in enumerate(operations):
                op_type = operation["type"]
                temp_output = os.path.join(temp_dir, f"step_{i}.mp4")

                logger.info(f"Processing operation {i}: {op_type}")

                if op_type == "audio":
                    success = self.audio_mixer.mix_audio(
                        video_path=current_path,
                        audio_path=operation["audio_path"],
                        output_path=temp_output,
                        volume=operation.get("volume", 0.5),
                        fade_in=operation.get("fade_in", 2.0),
                        fade_out=operation.get("fade_out", 2.0),
                    )

                elif op_type == "text":
                    success = self.text_overlay.apply_overlays(
                        video_path=current_path,
                        output_path=temp_output,
                        overlays=operation["overlays"],
                    )

                elif op_type == "filter":
                    filter_name = operation["filter_name"]
                    filter_params = {k: v for k, v in operation.items() if k not in ("type", "filter_name")}
                    success = self.video_filter.apply_filter(
                        video_path=current_path,
                        output_path=temp_output,
                        filter_name=filter_name,
                        **filter_params,
                    )

                else:
                    logger.error(f"Unknown operation type: {op_type}")
                    success = False

                if not success:
                    logger.error(f"Operation {i} ({op_type}) failed")
                    return False

                # Update current path for next operation
                current_path = temp_output
                logger.info(f"Operation {i} completed successfully")

            # Copy final result to output path
            if current_path != output_path:
                if os.path.exists(output_path):
                    os.remove(output_path)
                os.rename(current_path, output_path)

            logger.info(f"Post-processing completed: {output_path}")
            return True

        except Exception as e:
            logger.exception(f"Post-processing failed: {e}")
            return False

        finally:
            # Clean up temporary files
            try:
                if os.path.exists(temp_dir):
                    for f in os.listdir(temp_dir):
                        os.remove(os.path.join(temp_dir, f))
                    os.rmdir(temp_dir)
            except Exception as e:
                logger.warning(f"Failed to clean up temporary files: {e}")
