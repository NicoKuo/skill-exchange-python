import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_email(to_email, subject, body):
    """
    Send an HTML email via Gmail SMTP.

    Env vars:
    - SMTP_EMAIL
    - SMTP_PASSWORD

    Returns:
    - True on success
    - False on failure
    """
    smtp_email = os.getenv("SMTP_EMAIL", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()

    if not smtp_email or not smtp_password:
        print("[Email] SMTP_EMAIL or SMTP_PASSWORD is missing.")
        return False

    message = MIMEMultipart("alternative")
    message["From"] = smtp_email
    message["To"] = to_email
    message["Subject"] = subject
    message.attach(MIMEText(body, "html", "utf-8"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
            server.starttls()
            server.login(smtp_email, smtp_password)
            server.sendmail(smtp_email, [to_email], message.as_string())
        return True
    except Exception as exc:
        print(f"[Email] Failed to send email: {exc}")
        return False
