from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import quote


def build_mailto(to_emails: list[str], subject: str, body: str) -> str:
    return f"mailto:{','.join(to_emails)}?subject={quote(subject)}&body={quote(body)}"


def send_email_smtp(
    smtp_host: str,
    smtp_port: int,
    username: str,
    password: str,
    to_emails: list[str],
    subject: str,
    body: str,
    attachment_path: Path | None = None,
) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = username
    msg["To"] = ", ".join(to_emails)
    msg.set_content(body)
    if attachment_path and attachment_path.exists():
        msg.add_attachment(attachment_path.read_bytes(), maintype="application", subtype="pdf", filename=attachment_path.name)

    with smtplib.SMTP(smtp_host, smtp_port) as s:
        s.starttls()
        s.login(username, password)
        s.send_message(msg)
