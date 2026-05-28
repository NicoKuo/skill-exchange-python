import os
import resend


def _resend_config():
    resend_api_key_env = os.getenv("RESEND_API_KEY", "")
    resend_from_env = os.getenv("RESEND_FROM", "")

    return {
        "resend_api_key": resend_api_key_env.strip(),
        "resend_from": resend_from_env.strip(),
        "has_resend_api_key": bool(resend_api_key_env.strip()),
        "has_resend_from": bool(resend_from_env.strip()),
    }


def send_email(to_email, subject, body):
    """Send an HTML email using the Resend API."""
    print("[RESEND DEBUG] send_email called")

    resend_cfg = _resend_config()
    print(f"RESEND_API_KEY exists: {resend_cfg['has_resend_api_key']}")
    print(f"RESEND_FROM exists: {resend_cfg['has_resend_from']}")

    try:
        if not resend_cfg["resend_api_key"]:
            raise ValueError("RESEND_API_KEY is missing")
        if not resend_cfg["resend_from"]:
            raise ValueError("RESEND_FROM is missing")

        resend.api_key = resend_cfg["resend_api_key"]
        resend.Emails.send(
            {
                "from": resend_cfg["resend_from"],
                "to": [to_email],
                "subject": subject,
                "html": body,
            }
        )

        return True

    except Exception as exc:
        try:
            print("[RESEND ERROR]")
            print(type(exc).__name__)
            print(str(exc))
        except Exception:
            pass
        return False
