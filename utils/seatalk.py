"""
SeaTalk Integration Module
Send messages and files to SeaTalk webhook
"""

import os
import logging
import requests

WEBHOOK_URL = os.getenv("SEATALK_WEBHOOK_URL", "")

def seatalk_text(text: str):
    """Send text message to SeaTalk; tries few payload variants."""
    if not WEBHOOK_URL:
        raise RuntimeError("WEBHOOK_URL trống. Set env SEATALK_WEBHOOK_URL.")

    tries = [
        ("json_text", {"json": {"text": text}, "data": None}),
        ("json_content", {"json": {"content": text}, "data": None}),
        ("form_text", {"json": None, "data": {"text": text}}),
        ("form_content", {"json": None, "data": {"content": text}}),
        ("seatalk_tag_text", {"json": {"tag": "text", "text": {"content": text}}, "data": None}),
    ]

    last = None
    for label, payload in tries:
        try:
            r = requests.post(WEBHOOK_URL, json=payload["json"], data=payload["data"], timeout=12)
            last = r
            logging.info("[Seatalk %s] HTTP %s body=%s", label, r.status_code, (r.text or "")[:500])
            if r.status_code < 300:
                return {"ok": True, "status": r.status_code, "body": r.text, "variant": label}
        except Exception as e:
            logging.exception("[Seatalk %s] exception: %s", label, e)

    if last is None:
        raise RuntimeError("Seatalk request không thực hiện được (network error).")
    raise RuntimeError(f"Seatalk HTTP {last.status_code}: {(last.text or '')[:500]}")


def seatalk_file(bytes_data: bytes, filename: str, caption: str = ""):
    """Send file to SeaTalk (tries common field names)."""
    if not WEBHOOK_URL:
        raise RuntimeError("WEBHOOK_URL trống. Set env SEATALK_WEBHOOK_URL.")

    files = {
        "file": (filename, bytes_data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    }
    data = {"text": caption}

    r = requests.post(WEBHOOK_URL, data=data, files=files, timeout=30)
    logging.info("[Seatalk file] HTTP %s body=%s", r.status_code, (r.text or "")[:500])

    if r.status_code >= 300:
        # fallback with 'attachment'
        files2 = {"attachment": (filename, bytes_data, "application/octet-stream")}
        r2 = requests.post(WEBHOOK_URL, data={"text": caption}, files=files2, timeout=30)
        logging.info("[Seatalk file2] HTTP %s body=%s", r2.status_code, (r2.text or "")[:500])
        if r2.status_code >= 300:
            raise RuntimeError(
                f"Seatalk upload fail: {r.status_code}:{(r.text or '')[:200]} | {r2.status_code}:{(r2.text or '')[:200]}"
            )
        return {"ok": True, "status": r2.status_code, "body": r2.text, "variant": "attachment"}

    return {"ok": True, "status": r.status_code, "body": r.text, "variant": "file"}
