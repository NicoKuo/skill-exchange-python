import os
import requests


def _resend_config():
    resend_api_key_env = os.getenv("RESEND_API_KEY", "")
    resend_from_env = os.getenv("RESEND_FROM", "")

    return {
        "resend_api_key": resend_api_key_env.strip(),
        "resend_from": resend_from_env.strip(),
        "has_resend_api_key": bool(resend_api_key_env.strip()),
        "has_resend_from": bool(resend_from_env.strip()),
    }


def _log_resend_diagnostics(config):
    print("[RESEND DEBUG] RESEND_API_KEY exists:", config["has_resend_api_key"], flush=True)
    print("[RESEND DEBUG] RESEND_FROM exists:", config["has_resend_from"], flush=True)


def send_email(to_email, subject, body):
    """
    Send an HTML email via Resend HTTP API.

    Env vars:
    - RESEND_API_KEY
    - RESEND_FROM

    Returns:
    - True on success
    - False on failure
    """
    print("[RESEND DEBUG] send_email called", flush=True)
    try:
        config = _resend_config()

        _log_resend_diagnostics(config)

        if not config["resend_api_key"]:
            raise ValueError("RESEND_API_KEY is missing.")

        if not config["resend_from"]:
            raise ValueError("RESEND_FROM is missing.")

        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {config['resend_api_key']}",
                "Content-Type": "application/json",
            },
            json={
                "from": config["resend_from"],
                "to": [to_email],
                "subject": subject,
                "html": body,
            },
            timeout=20,
        )

        if response.status_code >= 400:
            raise RuntimeError(f"Resend API returned {response.status_code}: {response.text}")

        return True
    except Exception as exc:
        config = locals().get("config") or _resend_config()
        _log_resend_diagnostics(config)
        print("[RESEND ERROR]", flush=True)
        print(f"[RESEND ERROR] exception type: {type(exc).__name__}", flush=True)
        print(f"[RESEND ERROR] exception message: {exc}", flush=True)
        return False
