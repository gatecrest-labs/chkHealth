from __future__ import annotations

import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import Optional


_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "smtp_config.json"


def load_smtp_config(config_path: Path = _DEFAULT_CONFIG_PATH) -> dict:
    if not Path(config_path).exists():
        raise FileNotFoundError(f"smtp_config.json not found at {config_path}")
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def send_email(
    to: str,
    subject: str,
    body_html: str,
    attachment_data: Optional[str] = None,
    attachment_filename: Optional[str] = None,
    attachment_mime: Optional[str] = None,
    config_path: Path = _DEFAULT_CONFIG_PATH,
) -> None:
    cfg = load_smtp_config(config_path)

    msg = MIMEMultipart("mixed")
    msg["From"] = cfg["from_address"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body_html, "html"))

    if attachment_data and attachment_filename:
        mime_type = attachment_mime or "application/octet-stream"
        main_type, sub_type = mime_type.split("/", 1)
        if main_type == "text":
            part = MIMEText(attachment_data, sub_type)
        else:
            part = MIMEBase(main_type, sub_type)
            part.set_payload(attachment_data.encode())
            encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment",
                        filename=attachment_filename)
        msg.attach(part)

    host = cfg["host"]
    port = int(cfg.get("port", 587))
    use_tls = cfg.get("use_tls", True)

    with smtplib.SMTP(host, port) as server:
        if use_tls:
            server.starttls()
        username = cfg.get("username", "")
        password = cfg.get("password", "")
        if username:
            server.login(username, password)
        server.send_message(msg)
