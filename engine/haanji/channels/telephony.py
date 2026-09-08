"""Missed-call webhook contracts for Indian telephony providers.

POST /api/telephony/missed-call is provider-neutral: {"phone": "98XXXXXXXX"}.
The shapes below are what Exotel and Plivo actually send, so wiring a real
number is a five-line adapter, not a rewrite.

Exotel (passthru applet, call not picked):
    GET  https://<host>/api/telephony/missed-call?From=0987654321&To=0731XXXXXXX
    -> map From[-10:] to phone.

Plivo (hangup callback, HangupCause != NORMAL_CLEARING answered):
    POST form: From=+919876543210, To=+91731XXXXXXX, HangupCause=NO_ANSWER
    -> map From[-10:] to phone when HangupCause in {NO_ANSWER, BUSY, TIMEOUT}.
"""
MISSED_CAUSES = {"NO_ANSWER", "BUSY", "TIMEOUT", "ORIGINATOR_CANCEL"}
