import logging
import os
import smtplib
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def _safe_bool(value):
    return bool(str(value or "").strip())


def _resend_config():
    resend_api_key_env = os.getenv("RESEND_API_KEY", "")
    resend_from_env = os.getenv("RESEND_FROM", "")

    return {
        "resend_api_key": resend_api_key_env.strip(),
        "resend_from": resend_from_env.strip(),
        "has_resend_api_key": bool(resend_api_key_env.strip()),
        "has_resend_from": bool(resend_from_env.strip()),
    }


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
        "has_smtp_username": bool(smtp_username_env.strip()),
        "has_smtp_email": bool(smtp_email_env.strip()),
        "has_smtp_password": bool(smtp_password_env.strip()),
        "has_smtp_from": bool(smtp_from_env.strip()),
    }


def _log_resend_diagnostics(config):
    logger.debug(f"[Email][Resend] RESEND_API_KEY set={config['has_resend_api_key']}")
    logger.debug(f"[Email][Resend] RESEND_FROM set={config['has_resend_from']}")


def _log_smtp_diagnostics(config):
    logger.debug("[Email][SMTP] diagnostics:")
    logger.debug(f"[Email][SMTP] SMTP_HOST set={config['has_smtp_host']}")
    logger.debug(f"[Email][SMTP] SMTP_PORT set={config['has_smtp_port']}")
    logger.debug(f"[Email][SMTP] SMTP_USERNAME set={config['has_smtp_username']}")
    logger.debug(f"[Email][SMTP] SMTP_EMAIL set={config['has_smtp_email']}")
    logger.debug(f"[Email][SMTP] SMTP_FROM set={config['has_smtp_from']}")
    logger.debug(f"[Email][SMTP] SMTP_PASSWORD set={config['has_smtp_password']}")


def send_email(to_email, subject, body):
    """
    Send an HTML email using Resend API if configured, otherwise fallback to SMTP.

    Returns:
      (True, None) on success
      (False, error_message) on failure
    """
    # Prefer Resend if API key present
    try:
        resend_cfg = _resend_config()
        if resend_cfg["resend_api_key"]:
            _log_resend_diagnostics(resend_cfg)
            logger.debug("[Email] Using Resend API to send email")

            if not resend_cfg["resend_api_key"]:
                return False, "Resend API key is missing."
            if not resend_cfg["resend_from"]:
                return False, "Resend from address is missing."

            resp = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {resend_cfg['resend_api_key']}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": resend_cfg["resend_from"],
                    "to": [to_email],
                    "subject": subject,
                    "html": body,
                },
                timeout=20,
            )

            if resp.status_code >= 400:
                return False, f"Resend API returned {resp.status_code}: {resp.text}"

            return True, None

        # Fallback to SMTP
        smtp_cfg = _smtp_config()
        _log_smtp_diagnostics(smtp_cfg)

        if not smtp_cfg["smtp_username"]:
            return False, "SMTP username/email is missing."
        if not smtp_cfg["smtp_password"]:
            return False, "SMTP password is missing."
        if not smtp_cfg["smtp_from"]:
            return False, "SMTP from address is missing."

        logger.debug("[Email] Using SMTP to send email")

        message = MIMEMultipart("alternative")
        message["From"] = smtp_cfg["smtp_from"]
        message["To"] = to_email
        message["Subject"] = subject
        message.attach(MIMEText(body, "html", "utf-8"))

        with smtplib.SMTP(smtp_cfg["smtp_host"], smtp_cfg["smtp_port"], timeout=20) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_cfg["smtp_username"], smtp_cfg["smtp_password"])
            server.sendmail(smtp_cfg["smtp_from"], [to_email], message.as_string())

        return True, None

    except Exception as exc:
        logger.exception("send_email exception")
        try:
            # provide diagnostics in logs
            cfg = locals().get("resend_cfg") or locals().get("smtp_cfg") or _resend_config()
            if "resend_cfg" in locals():
                _log_resend_diagnostics(cfg)
            else:
                _log_smtp_diagnostics(cfg)
        except Exception:
            logger.debug("Failed to log email diagnostics")
        return False, str(exc)
