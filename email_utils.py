import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _safe_bool(value):
    return bool(str(value or "").strip())


def _smtp_config():
    smtp_host_env = os.getenv("SMTP_HOST", "")
    smtp_port_env = os.getenv("SMTP_PORT", "")
    smtp_username_env = os.getenv("SMTP_USERNAME", "")
    smtp_email_env = os.getenv("SMTP_EMAIL", "")
    smtp_password_env = os.getenv("SMTP_PASSWORD", "")
    smtp_from_env = os.getenv("SMTP_FROM", "")

    smtp_host = smtp_host_env.strip() or "smtp.gmail.com"
    smtp_port_raw = smtp_port_env.strip() or "587"

    try:
        smtp_port = int(smtp_port_raw)
    except ValueError:
        smtp_port = 587

    smtp_username = smtp_username_env.strip() or smtp_email_env.strip()
    smtp_password = smtp_password_env.strip()
    smtp_from = smtp_from_env.strip() or smtp_username

    return {
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "smtp_username": smtp_username,
        "smtp_password": smtp_password,
        "smtp_from": smtp_from,
        "has_smtp_host": bool(smtp_host_env.strip()),
        "has_smtp_port": bool(smtp_port_env.strip()),
        "has_smtp_username": bool(smtp_username_env.strip() or smtp_email_env.strip()),
        "has_smtp_password": bool(smtp_password_env.strip()),
        "has_smtp_from": bool(smtp_from_env.strip()),
    }


def _log_smtp_diagnostics(config):
    print("[Email] SMTP diagnostics:")
    print(f"[Email] SMTP_HOST set={config['has_smtp_host']} value={config['smtp_host']}")
    print(f"[Email] SMTP_PORT set={config['has_smtp_port']} value={config['smtp_port']}")
    print(f"[Email] SMTP_USERNAME set={config['has_smtp_username']}")
    print(f"[Email] SMTP_FROM set={config['has_smtp_from']} value={config['smtp_from']}")
    print(f"[Email] SMTP_PASSWORD set={config['has_smtp_password']}")


def send_email(to_email, subject, body):
    """
    Send an HTML email via Gmail SMTP.

    Env vars:
    - SMTP_HOST
    - SMTP_PORT
    - SMTP_USERNAME
    - SMTP_FROM
    - SMTP_EMAIL (fallback only)
    - SMTP_PASSWORD

    Returns:
    - True on success
    - False on failure
    """
    config = _smtp_config()
    smtp_password = config["smtp_password"]

    if not config["smtp_username"] or not smtp_password:
        _log_smtp_diagnostics(config)
        print("[Email] SMTP_USERNAME or SMTP_PASSWORD is missing.")
        return False

    message = MIMEMultipart("alternative")
    message["From"] = config["smtp_from"]
    message["To"] = to_email
    message["Subject"] = subject
    message.attach(MIMEText(body, "html", "utf-8"))

    try:
        with smtplib.SMTP(config["smtp_host"], config["smtp_port"], timeout=20) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(config["smtp_username"], smtp_password)
            server.sendmail(config["smtp_from"], [to_email], message.as_string())
        return True
    except Exception as exc:
        _log_smtp_diagnostics(config)
        print(f"[Email] Exception type: {type(exc).__name__}")
        print(f"[Email] Exception message: {exc}")
        return False
