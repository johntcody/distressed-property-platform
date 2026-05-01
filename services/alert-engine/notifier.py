"""Alert notification dispatch logic."""

from typing import Dict, Any


class AlertNotifier:
    CHANNELS = ["email", "sms", "webhook"]

    async def dispatch(self, alert: Dict[str, Any], channels: list = None) -> bool:
        """Send alert to one or more notification channels."""
        targets = channels or self.CHANNELS
        for channel in targets:
            await self._send(channel, alert)
        return True

    async def _send(self, channel: str, alert: Dict[str, Any]):
        # TODO: implement per-channel dispatch (SendGrid, Twilio, webhook POST)
        raise NotImplementedError
