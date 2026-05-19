#!/usr/bin/env python3
"""Audio mixing module for post-processing."""

import json
import logging
import os
import subprocess
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class AudioMixer:
    """Mix background music with video using FFmpeg."""

    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"):
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
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

    def extract_audio_info(self, audio_path: str) -> Optional[Dict[str, Any]]:
        """Extract audio file information using ffprobe.

        Args:
            audio_path: Path to audio file

        Returns:
            Dictionary with duration and other metadata, or None on failure
        """
        if not os.path.exists(audio_path):
            logger.error(f"Audio file not found: {audio_path}")
            return None

        cmd = [
            self.ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            audio_path,
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

            audio_stream = None
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "audio":
                    audio_stream = stream
                    break

            if not audio_stream:
                logger.error("No audio stream found")
                return None

            duration = 0.0
            if "duration" in audio_stream:
                duration = float(audio_stream["duration"])
            elif "duration" in data.get("format", {}):
                duration = float(data["format"]["duration"])

            info = {
                "duration": duration,
                "codec": audio_stream.get("codec_name", ""),
                "bitrate": int(data.get("format", {}).get("bit_rate", 0)),
                "sample_rate": int(audio_stream.get("sample_rate", 0)),
                "channels": int(audio_stream.get("channels", 0)),
            }

            logger.info(f"Audio info for {audio_path}: {info}")
            return info

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse FFprobe output: {e}")
            return None
        except (ValueError, KeyError) as e:
            logger.error(f"Failed to parse audio metadata: {e}")
            return None
        except Exception as e:
            logger.exception(f"FFprobe execution failed: {e}")
            return None

    def mix_audio(
        self,
        video_path: str,
        audio_path: str,
        output_path: str,
        volume: float = 0.5,
        fade_in: float = 2.0,
        fade_out: float = 2.0,
    ) -> bool:
        """Mix background music with video.

        Args:
            video_path: Path to input video file
            audio_path: Path to background audio file
            output_path: Path to output video file
            volume: Volume level for background music (0.0 to 1.0)
            fade_in: Fade in duration in seconds
            fade_out: Fade out duration in seconds

        Returns:
            True if successful, False otherwise
        """
        if not os.path.exists(video_path):
            logger.error(f"Video file not found: {video_path}")
            return False

        if not os.path.exists(audio_path):
            logger.error(f"Audio file not found: {audio_path}")
            return False

        # Get video duration to calculate fade out start time
        video_info_cmd = [
            self.ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            video_path,
        ]

        try:
            result = subprocess.run(
                video_info_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                logger.error(f"Failed to get video duration: {result.stderr}")
                return False

            video_data = json.loads(result.stdout)
            video_duration = float(video_data.get("format", {}).get("duration", 0))

            if video_duration <= 0:
                logger.error("Could not determine video duration")
                return False

            # Calculate fade out start time
            fade_out_start = max(0, video_duration - fade_out)

            # Build audio filter string
            audio_filter = (
                f"[1:a]volume={volume},"
                f"afade=t=in:ss=0:d={fade_in},"
                f"afade=t=out:st={fade_out_start}:d={fade_out}[a]"
            )

            # Build ffmpeg command
            args = [
                "-i", video_path,
                "-i", audio_path,
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "128k",
                "-filter_complex", audio_filter,
                "-map", "0:v",
                "-map", "[a]",
                "-shortest",
                output_path,
            ]

            success, error = self._run_ffmpeg(args)
            if not success:
                logger.error(f"Mix audio failed: {error}")
                return False

            logger.info(f"Audio mixed successfully: {output_path}")
            return True

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse video info: {e}")
            return False
        except (ValueError, KeyError) as e:
            logger.error(f"Failed to process video duration: {e}")
            return False
        except Exception as e:
            logger.exception(f"Audio mixing failed: {e}")
            return False
