import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class NotificationManager:
    """Manages desktop notifications, sounds, and clipboard operations for Linux systems."""

    def __init__(self, sound_dir: Optional[str] = None):
        """
        Initialize the notification manager.

        Args:
            sound_dir: Directory containing sound files. Defaults to 'extras/' relative to cwd.
        """
        self.sound_dir = Path(sound_dir) if sound_dir else Path("extras")
        self._check_dependencies()

    def _check_dependencies(self):
        """Check if required system commands are available."""
        self.has_notify_send = shutil.which("notify-send") is not None
        self.has_paplay = shutil.which("paplay") is not None
        self.has_xclip = shutil.which("xclip") is not None

        if not self.has_notify_send:
            logger.warning(
                "notify-send not found. Desktop notifications will be disabled."
            )
        if not self.has_paplay:
            logger.warning("paplay not found. Sound playback will be disabled.")
        if not self.has_xclip:
            logger.warning("xclip not found. Clipboard operations will be disabled.")

    def _send_desktop_notification(
        self, title: str, message: str, urgency: str = "normal"
    ) -> bool:
        """
        Send a desktop notification using notify-send.

        Args:
            title: Notification title
            message: Notification message
            urgency: Urgency level (low, normal, critical)

        Returns:
            True if successful, False otherwise
        """
        if not self.has_notify_send:
            logger.debug("Skipping notification - notify-send not available")
            return False

        if urgency not in ("low", "normal", "critical"):
            logger.warning(f"Invalid urgency level: {urgency}. Using 'normal'.")
            urgency = "normal"

        try:
            result = subprocess.run(
                ["notify-send", "-u", urgency, title, message],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                logger.error(f"notify-send failed: {result.stderr}")
                return False
            return True
        except subprocess.TimeoutExpired:
            logger.error("notify-send timed out")
            return False
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            return False

    def _play_sound(self, sound: str = "complete.oga") -> bool:
        """
        Play a sound file using paplay.

        Args:
            sound: Name of the sound file

        Returns:
            True if successful, False otherwise
        """
        if not self.has_paplay:
            logger.debug("Skipping sound - paplay not available")
            return False

        sound_path = self.sound_dir / sound

        if not sound_path.exists():
            logger.error(f"Sound file not found: {sound_path}")
            return False

        try:
            result = subprocess.run(
                ["paplay", str(sound_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                logger.error(f"paplay failed: {result.stderr}")
                return False
            return True
        except subprocess.TimeoutExpired:
            logger.error("paplay timed out")
            return False
        except Exception as e:
            logger.error(f"Error playing sound: {e}")
            return False

    def show_alert(
        self,
        title: str,
        message: str,
        urgency: str = "normal",
        sound: Optional[str] = "complete.oga",
        enable_notification: bool = True,
        enable_sound: bool = True,
    ) -> dict[str, bool]:
        """
        Show an alert with notification and sound.

        Args:
            title: Alert title
            message: Alert message
            urgency: Urgency level (low, normal, critical)
            sound: Name of sound file to play (None to disable)
            enable_notification: Whether to show desktop notification
            enable_sound: Whether to play sound

        Returns:
            Dictionary with success status of notification and sound
        """
        results = {"notification": False, "sound": False}

        if enable_notification:
            results["notification"] = self._send_desktop_notification(
                title, message, urgency
            )

        if enable_sound and sound:
            results["sound"] = self._play_sound(sound=sound)

        return results

    def copy_to_clipboard(self, data: str) -> bool:
        """
        Copy data to the system clipboard.

        Args:
            data: String data to copy

        Returns:
            True if successful, False otherwise
        """
        if not self.has_xclip:
            logger.error("xclip not available - cannot copy to clipboard")
            return False

        try:
            p = subprocess.Popen(
                ["xclip", "-selection", "clipboard"],
                stdin=subprocess.PIPE,
                close_fds=True,
            )
            p.communicate(input=data.encode())
            if p.returncode != 0:
                logger.error("xclip failed")
                return False
            return True
        except subprocess.TimeoutExpired:
            logger.error("xclip timed out")
            return False
        except Exception as e:
            logger.error(f"Error copying to clipboard: {e}")
            return False


# Global instance for convenience
_default_manager: Optional[NotificationManager] = None


def get_notification_manager(sound_dir: Optional[str] = None) -> NotificationManager:
    """
    Get the global notification manager instance.

    Args:
        sound_dir: Directory containing sound files (only used on first call)

    Returns:
        NotificationManager instance
    """
    global _default_manager
    if _default_manager is None:
        _default_manager = NotificationManager(sound_dir=sound_dir)
    return _default_manager


# Convenience functions for backward compatibility
def show_alert(
    title: str,
    message: str,
    urgency: str = "normal",
    sound: str = "complete.oga",
) -> dict[str, bool]:
    """Show an alert with notification and sound using the default manager."""
    return get_notification_manager().show_alert(title, message, urgency, sound)


def cp_to_clipboard(data: str) -> bool:
    """Copy data to clipboard using the default manager."""
    return get_notification_manager().copy_to_clipboard(data)
