"""A real phone number: the telephony bridge.

The engine's hot path takes text in and gives text out. This package puts a
phone call on each side of it: Twilio streams the caller's audio over a
WebSocket, a streaming recogniser turns it into partial and final
transcripts (the partials feed speculation, exactly as the browser's do), the
engine answers, and a synthesiser streams the reply back as 8 kHz μ-law.
Every vendor sits behind a small function so the bridge is tested with none
of them, and configured with environment variables only.
"""
