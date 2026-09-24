from sqlalchemy.orm import Session
from sqlalchemy import text
import glob
import json
import os
import random
import re
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
import schemas
from passlib.hash import bcrypt

# Dynamic .env loader
def load_env_config():
    # Search for .env in current directory or up to 5 parent directories
    current_dir = os.path.abspath(os.path.dirname(__file__))
    for _ in range(5):
        env_path = os.path.join(current_dir, ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if line_str and not line_str.startswith("#") and "=" in line_str:
                        k, v = line_str.split("=", 1)
                        os.environ[k.strip()] = v.strip().strip('"').strip("'")
            return
        parent = os.path.dirname(current_dir)
        if parent == current_dir:
            break
        current_dir = parent
    # If .env not found, rely on existing environment variables


def mail_sending_enabled() -> bool:
    """Kill-switch for real SMTP delivery.

    Dummy addresses (faculty2@cse.uiu.ac.bd, ...) always bounce back into the
    sender inbox ("address not found"). While testing with dummy data, set
    ENABLE_EMAIL_SENDING=false in .env — every mail path then only prints to
    the server console and never touches Gmail.
    """
    load_env_config()
    return str(os.environ.get("ENABLE_EMAIL_SENDING", "true")).strip().lower() not in (
        "false", "0", "no", "off")

# In-memory OTP cache (+history for admin display) with rate limiting
OTP_STORE = {}
OTP_HISTORY = {}
OTP_LAST_SENT = {}
OTP_SEND_COUNT = {}


def _otp_history_code(email: str) -> str:
    """Backward-compatible accessor: supports old plain-string entries."""
    try:
        v = OTP_HISTORY.get(str(email or "").lower(), "N/A")
        if isinstance(v, dict):
            return str(v.get("otp", "N/A"))
        return str(v)
    except Exception:
        return "N/A"

# Password hashing helpers
def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return bcrypt.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a bcrypt hash"""
    try:
        return bcrypt.verify(plain_password, hashed_password)
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Login-credentials JSON file sync
# ---------------------------------------------------------------------------
# The project keeps a JSON file (generated_passwords_*.json) holding every
# user's email + plain-text password so users can easily log in. Whenever a
# new user is successfully registered/approved, the backend appends (or
# updates) that user's entry here. This is strictly best-effort: any failure
# is logged and never breaks the registration flow.
# On hosted servers (Render) the disk is ephemeral, so set
# DISABLE_JSON_STORE=true to skip file writes there. Local behaviour unchanged.
def _json_store_disabled() -> bool:
    try:
        return str(os.environ.get("DISABLE_JSON_STORE", "")).strip().lower() in (
            "true", "1", "yes", "on")
    except Exception:
        return False

def _find_credentials_json():
    """Return the path of the existing credentials JSON file, if any."""
    try:
        base_dir = os.path.abspath(os.path.dirname(__file__))
        matches = glob.glob(os.path.join(base_dir, "generated_passwords_*.json"))
        if not matches:
            return None
        matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return matches[0]
    except Exception:
        return None

def _append_credentials_json(user_id, email, role, plain_password):
    """Append or update one user's login credentials in the JSON file.

    DEV-CONVENIENCE STORE (plain-text): keeps email + plain password so the
    developer can log in without remembering hashes. Matches by user_id first
    (so email changes don't create duplicates). If plain_password is None
    (email-only change), the old plain password is preserved.
    """
    if _json_store_disabled():
        return True
    try:
        if not email:
            return False
        path = _find_credentials_json()
        if not path:
            stamp = time.strftime("%Y%m%d_%H%M%S")
            path = os.path.join(
                os.path.abspath(os.path.dirname(__file__)),
                f"generated_passwords_{stamp}.json",
            )
        entries = []
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, list):
                    entries = loaded
            except Exception:
                entries = []
        norm_email = str(email).strip().lower()
        updated = False
        # 1) Match by user_id first (handles email change correctly)
        for entry in entries:
            try:
                if int(entry.get("user_id", -1)) == int(user_id):
                    entry["user_id"] = int(user_id)
                    entry["email"] = str(email).strip()
                    entry["role"] = role
                    if plain_password is not None:
                        entry["plain_password"] = str(plain_password)
                    updated = True
                    break
            except Exception:
                continue
        # 2) Fallback: match by email (handles legacy entries without user_id)
        if not updated:
            for entry in entries:
                try:
                    if str(entry.get("email", "")).strip().lower() == norm_email:
                        entry["user_id"] = int(user_id)
                        entry["email"] = str(email).strip()
                        entry["role"] = role
                        if plain_password is not None:
                            entry["plain_password"] = str(plain_password)
                        updated = True
                        break
                except Exception:
                    continue
        if not updated:
            entries.append({
                "user_id": int(user_id),
                "email": str(email).strip(),
                "role": role,
                "plain_password": str(plain_password) if plain_password is not None else "",
            })
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[CREDENTIALS JSON] Could not update login-credentials file: {e}")
        return False


def _remove_credentials_json(user_id):
    """Remove a user's entry from the login-credentials JSON file."""
    if _json_store_disabled():
        return True
    try:
        path = _find_credentials_json()
        if not path or not os.path.exists(path):
            return False
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, list):
            return False
        filtered = [e for e in loaded
                    if str(e.get("user_id", "")) != str(user_id)]
        if len(filtered) == len(loaded):
            return False
        with open(path, "w", encoding="utf-8") as f:
            json.dump(filtered, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[CREDENTIALS JSON] Could not remove entry: {e}")
        return False


def _sync_credentials_email_only(user_id, new_email, role):
    """Update only the email in JSON, preserving the stored plain password."""
    if _json_store_disabled():
        return True
    try:
        path = _find_credentials_json()
        if not path or not os.path.exists(path):
            return _append_credentials_json(user_id, new_email, role, None)
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, list):
            return False
        for entry in loaded:
            try:
                if int(entry.get("user_id", -1)) == int(user_id):
                    entry["email"] = str(new_email).strip()
                    entry["role"] = role
                    with open(path, "w", encoding="utf-8") as fw:
                        json.dump(loaded, fw, indent=2, ensure_ascii=False)
                    return True
            except Exception:
                continue
        return _append_credentials_json(user_id, new_email, role, None)
    except Exception as e:
        print(f"[CREDENTIALS JSON] Could not sync email: {e}")
        return False

def send_verification_otp(db: Session, email: str):
    _validate_student_contact_fields(email=email)
    if _email_taken(db, email):
        raise ValueError("This email address is already registered. Please use a different email.")

    load_env_config()

    # Rate limit: max 1 per 60s, max 5 per hour per email (anti-spam)
    now = time.time()
    key = email.lower()
    last = OTP_LAST_SENT.get(key, 0)
    if now - last < 60:
        raise ValueError("Please wait 60 seconds before requesting a new code.")
    window_start = now - 3600
    sends = [t for t in OTP_SEND_COUNT.get(key, []) if t > window_start]
    if len(sends) >= 5:
        raise ValueError("Too many OTP requests. Please try again after an hour.")
    sends.append(now)
    OTP_SEND_COUNT[key] = sends
    OTP_LAST_SENT[key] = now

    # Opportunistic expiry cleanup (prevents memory leak)
    for k in list(OTP_STORE.keys()):
        try:
            if OTP_STORE[k].get("expires_at", 0) < now:
                OTP_STORE.pop(k, None)
        except Exception:
            pass

    otp = f"{random.randint(100000, 999999)}"
    OTP_STORE[key] = {
        "otp": otp,
        "expires_at": now + 600  # 10 minutes validity
    }
    OTP_HISTORY[key] = {"otp": otp, "at": now}

    sender_email = os.environ.get("GMAIL_SENDER_EMAIL", "").strip()
    sender_password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    email_sent = False

    if sender_email and sender_password and mail_sending_enabled():
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"Your Verification Code for UIU Research Portal"
            msg["From"] = f"United International University Research Portal <{sender_email}>"
            msg["To"] = email
            msg["Reply-To"] = sender_email
            msg["Return-Path"] = sender_email
            msg["Date"] = formatdate(localtime=True)
            msg["Message-ID"] = make_msgid(domain=sender_email.split("@")[-1] if "@" in sender_email else "gmail.com")
            msg["X-Mailer"] = "ResearchPortalAuth/2.2"
            msg["MIME-Version"] = "1.0"
            msg["Precedence"] = "bulk"
            msg["List-Unsubscribe"] = f"<mailto:{sender_email}?subject=unsubscribe>, <https://uiu.ac.bd/unsubscribe>"
            msg["Auto-Submitted"] = "auto-generated"

            text_content = (
                f"Dear Applicant,\n\n"
                f"Thank you for registering with the United International University Research Management Portal.\n\n"
                f"Your verification code is: {otp}\n\n"
                f"This code will expire in 10 minutes.\n\n"
                f"If you did not request this registration, please disregard this email.\n\n"
                f"Best regards,\n"
                f"Research Management Portal Team\n"
                f"United International University"
            )
            html_content = f"""
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 520px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff; color: #1e293b;">
                <div style="text-align: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid #e2e8f0;">
                    <h1 style="color: #1e3a8a; margin: 0; font-size: 22px; font-weight: 700;">United International University</h1>
                    <p style="color: #64748b; margin: 4px 0 0 0; font-size: 14px;">Research Management Portal</p>
                </div>
                <p style="font-size: 15px; margin-bottom: 12px;">Dear Applicant,</p>
                <p style="font-size: 14px; color: #475569; margin-bottom: 20px;">Use the following 6-digit verification code to complete your registration:</p>
                <div style="text-align: center; margin: 24px 0;">
                    <span style="display: inline-block; font-size: 32px; font-weight: 700; letter-spacing: 6px; color: #0f172a; background-color: #f1f5f9; padding: 12px 28px; border-radius: 8px; border: 1px solid #cbd5e1; font-family: monospace;">{otp}</span>
                </div>
                <p style="font-size: 13px; color: #64748b; margin-top: 20px;">This code is valid for <strong>10 minutes</strong>.</p>
                <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0 16px 0;">
                <p style="font-size: 12px; color: #94a3b8; text-align: center; margin: 0;">Sent by Research Management Portal to {email}</p>
                <p style="font-size: 11px; color: #94a3b8; text-align: center; margin: 8px 0 0 0;">United International University, Dhaka, Bangladesh</p>
            </div>
            """
            msg.attach(MIMEText(text_content, "plain"))
            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, [email], msg.as_string())
            email_sent = True
        except Exception as e:
            print(f"[OTP SERVICE ERROR] Failed to send email via Gmail SMTP: {e}")

    print(f"\n==================================================")
    print(f"[OTP SERVICE] Verification Code for {email}: {otp}")
    print(f"Status: {'Sent successfully via Gmail' if email_sent else 'Printed to console (Configure GMAIL_SENDER_EMAIL & GMAIL_APP_PASSWORD in .env for real Gmail delivery)'}")
    print(f"==================================================\n")

    return {
        "message": f"Verification code sent to {email}.",
        "email": email,
        "sent": email_sent
    }

def verify_otp(email: str, otp: str) -> bool:
    record = OTP_STORE.get(email.lower())
    if not record:
        return False
    if time.time() > record["expires_at"]:
        OTP_STORE.pop(email.lower(), None)
        return False
    if str(record["otp"]).strip() != str(otp).strip():
        return False
    OTP_STORE.pop(email.lower(), None)
    return True


# ---- Forget password (separate store so signup OTP never clashes) ----
RESET_OTP_STORE = {}
RESET_LAST_SENT = {}
RESET_SEND_COUNT = {}


def _send_email_code(to_email: str, subject: str, title: str, intro: str, otp: str) -> bool:
    load_env_config()
    sender_email = os.environ.get("GMAIL_SENDER_EMAIL", "").strip()
    sender_password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    email_sent = False
    text_content = (
        f"Dear User,\n\n{intro}\n\nYour verification code is: {otp}\n\n"
        f"This code will expire in 10 minutes.\n\n"
        f"If you did not request this, please disregard this email.\n\n"
        f"Best regards,\nResearch Management Portal Team\nUnited International University"
    )
    html_content = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 520px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff; color: #1e293b;">
        <div style="text-align: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid #e2e8f0;">
            <h1 style="color: #1e3a8a; margin: 0; font-size: 22px; font-weight: 700;">United International University</h1>
            <p style="color: #64748b; margin: 4px 0 0 0; font-size: 14px;">Research Management Portal</p>
        </div>
        <h2 style="margin: 0 0 12px 0; font-size: 18px;">{title}</h2>
        <p style="font-size: 14px; color: #475569; margin-bottom: 20px;">{intro}</p>
        <div style="text-align: center; margin: 24px 0;">
            <span style="display: inline-block; font-size: 32px; font-weight: 700; letter-spacing: 6px; color: #0f172a; background-color: #f1f5f9; padding: 12px 28px; border-radius: 8px; border: 1px solid #cbd5e1; font-family: monospace;">{otp}</span>
        </div>
        <p style="font-size: 13px; color: #64748b; margin-top: 20px;">This code is valid for <strong>10 minutes</strong>.</p>
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0 16px 0;">
        <p style="font-size: 12px; color: #94a3b8; text-align: center; margin: 0;">Sent by Research Management Portal to {to_email}</p>
    </div>
    """
    if sender_email and sender_password and mail_sending_enabled():
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"United International University Research Portal <{sender_email}>"
            msg["To"] = to_email
            msg["Reply-To"] = sender_email
            msg["Date"] = formatdate(localtime=True)
            msg.attach(MIMEText(text_content, "plain"))
            msg.attach(MIMEText(html_content, "html"))
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, [to_email], msg.as_string())
            email_sent = True
        except Exception as e:
            print(f"[RESET OTP ERROR] Failed to send email: {e}")
    print(f"\n==================================================")
    print(f"[RESET OTP] Code for {to_email}: {otp}")
    print(f"Status: {'Sent via Gmail' if email_sent else 'Printed to console'}")
    print(f"==================================================\n")
    return email_sent


def send_password_reset_otp(db: Session, email: str):
    _validate_student_contact_fields(email=email)
    row = db.execute(text("SELECT user_id, email, role FROM user WHERE LOWER(TRIM(email)) = :e"),
                     {"e": str(email).strip().lower()}).fetchone()
    if not row:
        raise ValueError("This email is not registered.")
    now = time.time()
    key = str(email).strip().lower()
    if now - RESET_LAST_SENT.get(key, 0) < 60:
        raise ValueError("Please wait 60 seconds before requesting a new code.")
    sends = [t for t in RESET_SEND_COUNT.get(key, []) if t > now - 3600]
    if len(sends) >= 5:
        raise ValueError("Too many requests. Please try again after an hour.")
    sends.append(now)
    RESET_SEND_COUNT[key] = sends
    RESET_LAST_SENT[key] = now
    for k in list(RESET_OTP_STORE.keys()):
        try:
            if RESET_OTP_STORE[k].get("expires_at", 0) < now:
                RESET_OTP_STORE.pop(k, None)
        except Exception:
            pass
    otp = f"{random.randint(100000, 999999)}"
    RESET_OTP_STORE[key] = {"otp": otp, "expires_at": now + 600}
    sent = _send_email_code(email, "Your Password Reset Code for UIU Research Portal",
                            "Password Reset", "Use the code below to reset your password:", otp)
    return {"message": f"Reset code sent to {email}.", "email": email, "sent": sent}


def verify_reset_otp(email: str, otp: str) -> bool:
    record = RESET_OTP_STORE.get(str(email).strip().lower())
    if not record:
        return False
    if time.time() > record["expires_at"]:
        RESET_OTP_STORE.pop(str(email).strip().lower(), None)
        return False
    return str(record["otp"]).strip() == str(otp).strip()


def reset_password_with_otp(db: Session, email: str, otp: str, new_password: str):
    if not new_password or len(new_password) < 6:
        raise ValueError("New password must be at least 6 characters.")
    if not verify_reset_otp(email, otp):
        raise ValueError("Invalid or expired reset code.")
    row = db.execute(text("SELECT user_id, email, role FROM user WHERE LOWER(TRIM(email)) = :e"),
                     {"e": str(email).strip().lower()}).fetchone()
    if not row:
        raise ValueError("This email is not registered.")
    db.execute(text("UPDATE user SET password = :p WHERE user_id = :uid"),
               {"p": hash_password(new_password), "uid": row.user_id})
    db.commit()
    RESET_OTP_STORE.pop(str(email).strip().lower(), None)
    try:
        _append_credentials_json(row.user_id, row.email, row.role, new_password)
    except Exception:
        pass
    return {"message": "Password reset successful. Please login with your new password."}

def send_outcome_email(to_email: str, outcome: str, role: str, name: str = None):
    """
    Sends a formal outcome email (accepted or rejected) to the applicant.
    """
    if not to_email:
        return False
    load_env_config()
    sender_email = os.environ.get("GMAIL_SENDER_EMAIL", "").strip()
    sender_password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()

    # Dynamic role-based display name (never hardcoded to a single role).
    # Each outgoing email explicitly names the role the user applied for.
    _role_key = str(role or "").strip().lower()
    if _role_key.startswith("student"):
        role_display = "Student"
    elif _role_key.startswith("faculty"):
        role_display = "Faculty Member"
    elif _role_key == "admin" or "admin" in _role_key:
        role_display = "Administrator"
    else:
        role_display = str(role).strip().title() if str(role or "").strip() else "Applicant"
    is_accepted = outcome.lower() == "accepted"
    salutation = f"Dear {name}," if name else "Dear Applicant,"

    if is_accepted:
        subject = f"Your {role_display} Application has been Approved"
        plain_text = (
            f"{salutation}\n\n"
            f"We are pleased to inform you that your request to join the United International University Research Management Portal "
            f"as a {role_display} (requested role: {role_display}) has been approved by the administration.\n\n"
            f"You can now log in to the portal using your registered email ({to_email}) and your password.\n\n"
            f"Best regards,\n"
            f"Administration Team\n"
            f"Research Management Portal\n"
            f"United International University"
        )
        status_box = f"""
        <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 16px; margin: 20px 0;">
            <p style="margin: 0; font-size: 14px; color: #166534; font-weight: 600;">Account Activated</p>
            <p style="margin: 6px 0 0 0; font-size: 13px; color: #15803d;">
                You can now log in to the portal using your registered email (<strong>{to_email}</strong>) and your password.
            </p>
        </div>
        """
        title = "Application Approved"
        title_color = "#16a34a"
        main_msg = f"We are pleased to inform you that your request to join the <strong>Research Management Portal</strong> as a <strong>{role_display}</strong> (requested role: <strong>{role_display}</strong>) has been <strong>accepted</strong> by the administration."
    else:
        subject = f"Update on Your {role_display} Application"
        plain_text = (
            f"{salutation}\n\n"
            f"Thank you for your interest in joining the United International University Research Management Portal.\n\n"
            f"After administrative review, we regret to inform you that your request to create an account "
            f"as a {role_display} (requested role: {role_display}) has not been approved at this time.\n\n"
            f"If you have any questions or require additional clarification, please feel free to reach out to the portal administration.\n\n"
            f"Best regards,\n"
            f"Administration Team\n"
            f"Research Management Portal\n"
            f"United International University"
        )
        status_box = f"""
        <div style="background-color: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 16px; margin: 20px 0;">
            <p style="margin: 0; font-size: 13px; color: #991b1b;">
                If you believe this decision was made in error or require additional clarification, please contact the portal administration.
            </p>
        </div>
        """
        title = "Application Status Update"
        title_color = "#dc2626"
        main_msg = f"After administrative review, we regret to inform you that your request to create an account as a <strong>{role_display}</strong> (requested role: <strong>{role_display}</strong>) has been <strong>rejected</strong>."

    html_content = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 520px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff; color: #1e293b;">
        <div style="text-align: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid #e2e8f0;">
            <h1 style="color: #1e3a8a; margin: 0; font-size: 22px; font-weight: 700;">United International University</h1>
            <p style="color: #64748b; margin: 4px 0 0 0; font-size: 14px;">Research Management Portal</p>
        </div>
        <h2 style="color: {title_color}; margin: 0 0 16px 0; font-size: 20px;">{title}</h2>
        <p style="font-size: 15px; margin-bottom: 12px;">{salutation}</p>
        <p style="font-size: 14px; color: #334155; line-height: 1.6;">{main_msg}</p>
        {status_box}
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0 16px 0;">
        <p style="font-size: 12px; color: #94a3b8; text-align: center; margin: 0;">Sent by Research Management Portal to {to_email}</p>
        <p style="font-size: 11px; color: #94a3b8; text-align: center; margin: 8px 0 0 0;">United International University, Dhaka, Bangladesh</p>
    </div>
    """

    email_sent = False
    if sender_email and sender_password and mail_sending_enabled():
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"United International University Research Portal <{sender_email}>"
            msg["To"] = to_email
            msg["Reply-To"] = sender_email
            msg["Return-Path"] = sender_email
            msg["Date"] = formatdate(localtime=True)
            msg["Message-ID"] = make_msgid(domain=sender_email.split("@")[-1] if "@" in sender_email else "gmail.com")
            msg["X-Mailer"] = "ResearchPortalAuth/2.2"
            msg["MIME-Version"] = "1.0"
            msg["Precedence"] = "bulk"
            msg["List-Unsubscribe"] = f"<mailto:{sender_email}?subject=unsubscribe>, <https://uiu.ac.bd/unsubscribe>"
            msg["Auto-Submitted"] = "auto-generated"

            msg.attach(MIMEText(plain_text, "plain"))
            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, [to_email], msg.as_string())
            email_sent = True
        except Exception as e:
            print(f"[OUTCOME EMAIL ERROR] Failed to send outcome email to {to_email}: {e}")

    print(f"\n==================================================")
    print(f"[OUTCOME EMAIL] Decision for {to_email}: {outcome.upper()} ({role_display})")
    print(f"Status: {'Sent successfully via Gmail' if email_sent else 'Printed to console (Configure GMAIL_SENDER_EMAIL & GMAIL_APP_PASSWORD in .env for real Gmail delivery)'}")
    print(f"==================================================\n")
    return email_sent


def send_application_decision_email(to_email: str, decision: str, project_title: str = None,
                                    faculty_name: str = None, feedback: str = None,
                                    student_name: str = None):
    """
    Sends a project-application-specific decision email to the student applicant.
    This is separate from send_outcome_email() which is only for portal signup.
    """
    if not to_email:
        return False
    load_env_config()
    sender_email = os.environ.get("GMAIL_SENDER_EMAIL", "").strip()
    sender_password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()

    dec = str(decision or "").strip().lower()
    is_approved = (dec == "approved" or dec == "accepted")
    salutation = f"Dear {student_name}," if student_name else "Dear Applicant,"
    safe_project = project_title or "the applied project"
    safe_faculty = faculty_name or "the faculty supervisor"

    if is_approved:
        subject = f"Your Application for '{safe_project}' has been Approved"
        plain_text = (
            f"{salutation}\n\n"
            f"Congratulations! Your application for the research project '{safe_project}' "
            f"(supervised by {safe_faculty}) has been approved.\n\n"
            f"Please contact your faculty supervisor for the next steps.\n\n"
            + (f"Faculty Feedback: {feedback}\n\n" if feedback else "") +
            f"Best regards,\n"
            f"Research Management Portal\n"
            f"United International University"
        )
        title = "Application Approved"
        title_color = "#16a34a"
        main_msg = (f"Your application for the research project <strong>{safe_project}</strong> "
                    f"(supervised by <strong>{safe_faculty}</strong>) has been <strong>approved</strong>.")
        status_box = f"""
        <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 16px; margin: 20px 0;">
            <p style="margin: 0; font-size: 14px; color: #166534; font-weight: 600;">Next Step</p>
            <p style="margin: 6px 0 0 0; font-size: 13px; color: #15803d;">
                Please contact your faculty supervisor ({safe_faculty}) for the next steps.
            </p>
        </div>
        """
    else:
        subject = f"Update on Your Application for '{safe_project}'"
        plain_text = (
            f"{salutation}\n\n"
            f"Thank you for applying to the research project '{safe_project}' "
            f"(supervised by {safe_faculty}).\n\n"
            f"After review, we regret to inform you that your application has not been approved at this time.\n\n"
            + (f"Faculty Feedback: {feedback}\n\n" if feedback else "") +
            f"You are welcome to apply to other active projects on the portal.\n\n"
            f"Best regards,\n"
            f"Research Management Portal\n"
            f"United International University"
        )
        title = "Application Status Update"
        title_color = "#dc2626"
        main_msg = (f"After review, we regret to inform you that your application for the research project "
                    f"<strong>{safe_project}</strong> (supervised by <strong>{safe_faculty}</strong>) "
                    f"has been <strong>rejected</strong>.")
        status_box = f"""
        <div style="background-color: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 16px; margin: 20px 0;">
            <p style="margin: 0; font-size: 13px; color: #991b1b;">
                You are welcome to apply to other active projects on the portal.
            </p>
        </div>
        """

    feedback_box = ""
    if feedback:
        # Escape minimal HTML for feedback display
        safe_fb = str(feedback).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        feedback_box = f"""
        <div style="background-color: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 16px; margin: 20px 0;">
            <p style="margin: 0 0 6px 0; font-size: 13px; color: #92400e; font-weight: 600;">Faculty Feedback</p>
            <p style="margin: 0; font-size: 13px; color: #78350f;">{safe_fb}</p>
        </div>
        """

    html_content = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 520px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff; color: #1e293b;">
        <div style="text-align: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid #e2e8f0;">
            <h1 style="color: #1e3a8a; margin: 0; font-size: 22px; font-weight: 700;">United International University</h1>
            <p style="color: #64748b; margin: 4px 0 0 0; font-size: 14px;">Research Management Portal</p>
        </div>
        <h2 style="color: {title_color}; margin: 0 0 16px 0; font-size: 20px;">{title}</h2>
        <p style="font-size: 15px; margin-bottom: 12px;">{salutation}</p>
        <p style="font-size: 14px; color: #334155; line-height: 1.6;">{main_msg}</p>
        {status_box}
        {feedback_box}
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0 16px 0;">
        <p style="font-size: 12px; color: #94a3b8; text-align: center; margin: 0;">Sent by Research Management Portal to {to_email}</p>
        <p style="font-size: 11px; color: #94a3b8; text-align: center; margin: 8px 0 0 0;">United International University, Dhaka, Bangladesh</p>
    </div>
    """

    email_sent = False
    if sender_email and sender_password and mail_sending_enabled():
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"United International University Research Portal <{sender_email}>"
            msg["To"] = to_email
            msg["Reply-To"] = sender_email
            msg["Return-Path"] = sender_email
            msg["Date"] = formatdate(localtime=True)
            msg["Message-ID"] = make_msgid(domain=sender_email.split("@")[-1] if "@" in sender_email else "gmail.com")
            msg["X-Mailer"] = "ResearchPortalAuth/2.2"
            msg["MIME-Version"] = "1.0"
            msg["Precedence"] = "bulk"
            msg["List-Unsubscribe"] = f"<mailto:{sender_email}?subject=unsubscribe>, <https://uiu.ac.bd/unsubscribe>"
            msg["Auto-Submitted"] = "auto-generated"

            msg.attach(MIMEText(plain_text, "plain"))
            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, [to_email], msg.as_string())
            email_sent = True
        except Exception as e:
            print(f"[APPLICATION EMAIL ERROR] Failed to send application decision email to {to_email}: {e}")

    print(f"\n==================================================")
    print(f"[APPLICATION EMAIL] Decision for {to_email}: {dec.upper()} (Project: {safe_project})")
    print(f"Status: {'Sent successfully via Gmail' if email_sent else 'Printed to console (Configure GMAIL_SENDER_EMAIL & GMAIL_APP_PASSWORD in .env for real Gmail delivery)'}")
    print(f"==================================================\n")
    return email_sent


def _faculty_contact(db: Session, faculty_id):
    """Best-effort lookup of a faculty member's name + login email."""
    name, email = None, ""
    try:
        frow = db.execute(text("SELECT name FROM faculty WHERE faculty_id = :f"),
                          {"f": faculty_id}).fetchone()
        if frow:
            name = getattr(frow, "name", None)
    except Exception:
        pass
    try:
        urow = db.execute(text("SELECT email FROM user WHERE user_id = :u"),
                          {"u": faculty_id}).fetchone()
        if urow:
            email = getattr(urow, "email", "") or ""
    except Exception:
        pass
    return name, email


def _reviewer_email(db: Session, actor_id):
    """Best-effort lookup of the admin/superadmin who decided the request."""
    try:
        if actor_id is None:
            return ""
        rrow = db.execute(text("SELECT email FROM user WHERE user_id = :u"),
                          {"u": int(actor_id)}).fetchone()
        return (rrow.email if rrow else "") or ""
    except Exception:
        return ""


def _student_contact(db: Session, student_id):
    """Best-effort lookup of a student's name + login email."""
    name, email = None, ""
    try:
        srow = db.execute(text("SELECT name FROM student WHERE student_id = :s"),
                          {"s": student_id}).fetchone()
        if srow:
            name = getattr(srow, "name", None)
    except Exception:
        pass
    try:
        urow = db.execute(text("SELECT email FROM user WHERE user_id = :u"),
                          {"u": student_id}).fetchone()
        if urow:
            email = getattr(urow, "email", "") or ""
    except Exception:
        pass
    return name, email


def _all_admin_emails(db: Session):
    """All admin accounts — only used as a legacy fallback, never for broadcast."""
    try:
        rows = db.execute(text("SELECT user_id, email FROM user WHERE role = 'admin'")).fetchall()
        return [(int(r.user_id), (r.email or "")) for r in rows if getattr(r, "email", "")]
    except Exception:
        return []


def _originating_admin(db: Session, notification_id, action_hint: str = ""):
    """Find the admin/superadmin behind an earlier decision/proposal.

    Looks through the permanent AdminActivity mirror for the newest entry
    referencing this notification. Returns (actor_id, email) or (None, "")
    when the action predates activity logging.
    """
    try:
        hint = str(action_hint or "").strip().lower()
        rows = db.execute(text("SELECT payload FROM notification WHERE type = 'AdminActivity'"
                               " ORDER BY notification_id DESC LIMIT 300")).fetchall()
        fallback = (None, "")
        for r in rows:
            try:
                data = json.loads(r.payload)
            except Exception:
                continue
            try:
                if int(data.get("notification_id", -1)) != int(notification_id):
                    continue
            except Exception:
                continue
            aid = data.get("actor_id")
            aemail = data.get("admin_email") or _reviewer_email(db, aid)
            if hint and hint not in str(data.get("action", "")).lower():
                if fallback[0] is None and aid is not None:
                    fallback = (aid, aemail)
                continue
            return (aid, aemail)
        return fallback
    except Exception:
        return (None, "")


def send_admin_notice_email(to_email: str, title: str, intro: str,
                            details=None, next_step: str = "", tone: str = "info"):
    """Generic classy notice email addressed to an administrator.

    tone: 'success' (green), 'danger' (red) or 'info' (blue).
    details: list of (label, value) rows shown in a detail box.
    """
    if not to_email:
        return False
    load_env_config()
    sender_email = os.environ.get("GMAIL_SENDER_EMAIL", "").strip()
    sender_password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()

    colors = {
        "success": ("#16a34a", "#f0fdf4", "#bbf7d0", "#166534", "#15803d"),
        "danger": ("#dc2626", "#fef2f2", "#fecaca", "#991b1b", "#991b1b"),
    }
    title_color, box_bg, box_bd, box_head, box_text = colors.get(
        tone, ("#1d4ed8", "#eff6ff", "#bfdbfe", "#1e40af", "#1e40af"))

    def _esc(v):
        return str(v if v is not None else "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    detail_rows = list(details or [])
    detail_html = "".join([
        f"""<div style="display: flex; gap: 8px; font-size: 13px; padding: 7px 0; border-bottom: 1px solid #f1f5f9;">
            <span style="min-width: 130px; color: #64748b; font-weight: 600;">{_esc(k)}</span>
            <span style="color: #0f172a; font-weight: 500;">{_esc(v)}</span>
        </div>""" for k, v in detail_rows
    ])
    detail_plain = "\n".join([f"{k}: {v}" for k, v in detail_rows])
    next_box = ""
    if next_step:
        next_box = f"""
        <div style="background-color: {box_bg}; border: 1px solid {box_bd}; border-radius: 8px; padding: 16px; margin: 20px 0;">
            <p style="margin: 0; font-size: 13px; color: {box_text};">{_esc(next_step)}</p>
        </div>
        """

    plain_text = (
        f"Dear Administrator,\n\n"
        f"{intro}\n\n"
        + (f"{detail_plain}\n\n" if detail_plain else "")
        + (f"{next_step}\n\n" if next_step else "") +
        f"Best regards,\n"
        f"Research Management Portal\n"
        f"United International University"
    )
    html_content = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 520px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff; color: #1e293b;">
        <div style="text-align: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid #e2e8f0;">
            <h1 style="color: #1e3a8a; margin: 0; font-size: 22px; font-weight: 700;">United International University</h1>
            <p style="color: #64748b; margin: 4px 0 0 0; font-size: 14px;">Research Management Portal</p>
        </div>
        <h2 style="color: {title_color}; margin: 0 0 16px 0; font-size: 20px;">{_esc(title)}</h2>
        <p style="font-size: 15px; margin-bottom: 12px;">Dear Administrator,</p>
        <p style="font-size: 14px; color: #334155; line-height: 1.6;">{_esc(intro)}</p>
        {"<div style='background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px 16px; margin: 20px 0;'>" + detail_html + "</div>" if detail_html else ""}
        {next_box}
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0 16px 0;">
        <p style="font-size: 12px; color: #94a3b8; text-align: center; margin: 0;">Sent by Research Management Portal to {to_email}</p>
        <p style="font-size: 11px; color: #94a3b8; text-align: center; margin: 8px 0 0 0;">United International University, Dhaka, Bangladesh</p>
    </div>
    """

    email_sent = False
    if sender_email and sender_password and mail_sending_enabled():
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = title
            msg["From"] = f"United International University Research Portal <{sender_email}>"
            msg["To"] = to_email
            msg["Reply-To"] = sender_email
            msg["Return-Path"] = sender_email
            msg["Date"] = formatdate(localtime=True)
            msg["Message-ID"] = make_msgid(domain=sender_email.split("@")[-1] if "@" in sender_email else "gmail.com")
            msg["X-Mailer"] = "ResearchPortalAuth/2.2"
            msg["MIME-Version"] = "1.0"
            msg["Precedence"] = "bulk"
            msg["List-Unsubscribe"] = f"<mailto:{sender_email}?subject=unsubscribe>, <https://uiu.ac.bd/unsubscribe>"
            msg["Auto-Submitted"] = "auto-generated"

            msg.attach(MIMEText(plain_text, "plain"))
            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, [to_email], msg.as_string())
            email_sent = True
        except Exception as e:
            print(f"[ADMIN NOTICE EMAIL ERROR] Failed to send '{title}' to {to_email}: {e}")

    print(f"\n==================================================")
    print(f"[ADMIN NOTICE EMAIL] '{title}' for {to_email}")
    print(f"Status: {'Sent successfully via Gmail' if email_sent else 'Printed to console (Configure GMAIL_SENDER_EMAIL & GMAIL_APP_PASSWORD in .env for real Gmail delivery)'}")
    print(f"==================================================\n")
    return email_sent


def _email_response_to_originator(db: Session, notification_id, notif_type: str,
                                  responder_label: str, decision: str, summary: str):
    """Email a faculty/student Yes-No response to the originating admin only.

    Falls back to all admins solely for legacy rows that predate activity logging.
    """
    try:
        aid, aemail = _originating_admin(db, notification_id)
        recipients = [(aid, aemail)] if aemail else []
        if not recipients:
            recipients = _all_admin_emails(db)
            if not recipients:
                return False
        accepted = str(decision or "").strip().lower() == "accepted"
        for _aid, _email in recipients:
            try:
                send_admin_notice_email(
                    to_email=_email,
                    title=f"{responder_label} {('Accepted' if accepted else 'Rejected')} Your Proposal",
                    intro=(f"{responder_label} has {('accepted' if accepted else 'rejected')} "
                           f"the proposal referenced below ({notif_type}, request #{notification_id})."),
                    details=[("Response", "Accepted" if accepted else "Rejected"),
                             ("Details", summary or "—")],
                    next_step=("No further action is needed. This is recorded in the superadmin audit log."
                               if accepted else
                               "The proposed changes were not applied. You may revise and propose again if needed."),
                    tone=("success" if accepted else "danger"))
            except Exception:
                pass
        return True
    except Exception:
        return False


def send_new_application_email(to_email: str, faculty_name: str, project_title: str,
                               applicant_name: str, applicant_cgpa=None, applicant_department=None,
                               motivation: str = None):
    """A student just applied — tell the supervising faculty with key details."""
    if not to_email:
        return False
    load_env_config()
    sender_email = os.environ.get("GMAIL_SENDER_EMAIL", "").strip()
    sender_password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()

    salutation = f"Dear {faculty_name}," if faculty_name else "Dear Faculty Member,"
    safe_project = project_title or "your project"
    safe_applicant = applicant_name or "A student"

    def _esc(v):
        return str(v if v is not None else "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    rows = [("Project", safe_project), ("Applicant", safe_applicant)]
    if applicant_cgpa:
        rows.append(("Applicant CGPA", applicant_cgpa))
    if applicant_department:
        rows.append(("Applicant Department", applicant_department))
    detail_plain = "\n".join([f"{k}: {v}" for k, v in rows])
    detail_html = "".join([
        f"""<div style="display: flex; gap: 8px; font-size: 13px; padding: 7px 0; border-bottom: 1px solid #f1f5f9;">
            <span style="min-width: 130px; color: #64748b; font-weight: 600;">{_esc(k)}</span>
            <span style="color: #0f172a; font-weight: 500;">{_esc(v)}</span>
        </div>""" for k, v in rows
    ])
    motive_plain = f"Motivation: {motivation}\n\n" if motivation else ""
    motive_box = ""
    if motivation:
        motive_box = f"""
        <div style="background-color: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 16px; margin: 20px 0;">
            <p style="margin: 0 0 6px 0; font-size: 13px; color: #92400e; font-weight: 600;">Applicant Motivation</p>
            <p style="margin: 0; font-size: 13px; color: #78350f;">{_esc(motivation)}</p>
        </div>
        """

    subject = f"New Application for '{safe_project}' from {safe_applicant}"
    plain_text = (
        f"{salutation}\n\n"
        f"{safe_applicant} has applied to your research project '{safe_project}'.\n\n"
        f"{detail_plain}\n"
        f"{motive_plain}"
        f"Please open the Application Management module to review, approve or reject this application.\n\n"
        f"Best regards,\n"
        f"Research Management Portal\n"
        f"United International University"
    )
    html_content = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 520px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff; color: #1e293b;">
        <div style="text-align: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid #e2e8f0;">
            <h1 style="color: #1e3a8a; margin: 0; font-size: 22px; font-weight: 700;">United International University</h1>
            <p style="color: #64748b; margin: 4px 0 0 0; font-size: 14px;">Research Management Portal</p>
        </div>
        <h2 style="color: #1d4ed8; margin: 0 0 16px 0; font-size: 20px;">New Project Application</h2>
        <p style="font-size: 15px; margin-bottom: 12px;">{salutation}</p>
        <p style="font-size: 14px; color: #334155; line-height: 1.6;"><strong>{_esc(safe_applicant)}</strong> has applied to your research project <strong>{_esc(safe_project)}</strong>.</p>
        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px 16px; margin: 20px 0;">
            {detail_html}
        </div>
        {motive_box}
        <div style="background-color: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 16px; margin: 20px 0;">
            <p style="margin: 0; font-size: 13px; color: #1e40af;">Please open the Application Management module to review, approve or reject this application.</p>
        </div>
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0 16px 0;">
        <p style="font-size: 12px; color: #94a3b8; text-align: center; margin: 0;">Sent by Research Management Portal to {to_email}</p>
        <p style="font-size: 11px; color: #94a3b8; text-align: center; margin: 8px 0 0 0;">United International University, Dhaka, Bangladesh</p>
    </div>
    """

    email_sent = False
    if sender_email and sender_password and mail_sending_enabled():
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"United International University Research Portal <{sender_email}>"
            msg["To"] = to_email
            msg["Reply-To"] = sender_email
            msg["Return-Path"] = sender_email
            msg["Date"] = formatdate(localtime=True)
            msg["Message-ID"] = make_msgid(domain=sender_email.split("@")[-1] if "@" in sender_email else "gmail.com")
            msg["X-Mailer"] = "ResearchPortalAuth/2.2"
            msg["MIME-Version"] = "1.0"
            msg["Precedence"] = "bulk"
            msg["List-Unsubscribe"] = f"<mailto:{sender_email}?subject=unsubscribe>, <https://uiu.ac.bd/unsubscribe>"
            msg["Auto-Submitted"] = "auto-generated"

            msg.attach(MIMEText(plain_text, "plain"))
            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, [to_email], msg.as_string())
            email_sent = True
        except Exception as e:
            print(f"[NEW APPLICATION EMAIL ERROR] Failed to send to {to_email}: {e}")

    print(f"\n==================================================")
    print(f"[NEW APPLICATION EMAIL] '{safe_project}' applicant {safe_applicant} for {to_email}")
    print(f"Status: {'Sent successfully via Gmail' if email_sent else 'Printed to console (Configure GMAIL_SENDER_EMAIL & GMAIL_APP_PASSWORD in .env for real Gmail delivery)'}")
    print(f"==================================================\n")
    return email_sent


def send_project_request_outcome_email(to_email: str, request_kind: str, outcome: str,
                                       project_title: str = None, description: str = None,
                                       required_skill: str = None, faculty_name: str = None,
                                       reviewer_email: str = None):
    """
    Detailed decision email to a faculty member for their project
    creation / deletion request (accepted or rejected by administration).
    """
    if not to_email:
        return False
    load_env_config()
    sender_email = os.environ.get("GMAIL_SENDER_EMAIL", "").strip()
    sender_password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()

    kind = str(request_kind or "creation").strip().lower()
    is_creation = (kind != "deletion")
    out = str(outcome or "").strip().lower()
    is_accepted = (out in ("accepted", "approved"))
    salutation = f"Dear {faculty_name}," if faculty_name else "Dear Faculty Member,"
    safe_title = project_title or "your project"
    reviewed_by = f"Reviewed by: {reviewer_email}" if reviewer_email else "Reviewed by the portal administration"

    def _esc(v):
        return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    if is_creation and is_accepted:
        subject = f"Your Project Creation Request for '{safe_title}' has been Approved"
        relevance = ("Your request to create the research project has been approved. "
                     "One final step remains: please open your Notification Hub and confirm "
                     "the creation — the project will be published only after your confirmation.")
        next_box = """
        <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 16px; margin: 20px 0;">
            <p style="margin: 0; font-size: 14px; color: #166534; font-weight: 600;">Next Step — Confirmation Required</p>
            <p style="margin: 6px 0 0 0; font-size: 13px; color: #15803d;">
                Please open your Notification Hub and confirm this creation. The project goes live only after your confirmation.
            </p>
        </div>
        """
        next_plain = ("Next step: please open your Notification Hub and confirm this creation. "
                      "The project goes live only after your confirmation.")
        title, title_color, outcome_word = "Project Creation Approved", "#16a34a", "approved"
    elif is_creation:
        subject = f"Update on Your Project Creation Request for '{safe_title}'"
        relevance = ("After administrative review, your request to create the research project "
                     "has not been approved at this time. Your existing projects remain unchanged. "
                     "If you need clarification, please contact the portal administration.")
        next_box = """
        <div style="background-color: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 16px; margin: 20px 0;">
            <p style="margin: 0; font-size: 13px; color: #991b1b;">
                Your existing projects remain unchanged. Contact the portal administration if you need clarification.
            </p>
        </div>
        """
        next_plain = ("Your existing projects remain unchanged. "
                      "Contact the portal administration if you need clarification.")
        title, title_color, outcome_word = "Project Creation Status Update", "#dc2626", "rejected"
    elif is_accepted:
        subject = f"Your Project Deletion Request for '{safe_title}' has been Approved"
        relevance = ("Your request to delete the research project has been approved. "
                     "The project has been permanently removed along with all of its applications.")
        next_box = """
        <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 16px; margin: 20px 0;">
            <p style="margin: 0; font-size: 14px; color: #166534; font-weight: 600;">What Changed</p>
            <p style="margin: 6px 0 0 0; font-size: 13px; color: #15803d;">
                The project has been permanently removed along with all of its applications.
            </p>
        </div>
        """
        next_plain = "The project has been permanently removed along with all of its applications."
        title, title_color, outcome_word = "Project Deletion Approved", "#16a34a", "approved"
    else:
        subject = f"Update on Your Project Deletion Request for '{safe_title}'"
        relevance = ("After administrative review, your request to delete the research project "
                     "has not been approved at this time. The project remains active and unchanged.")
        next_box = """
        <div style="background-color: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 16px; margin: 20px 0;">
            <p style="margin: 0; font-size: 13px; color: #991b1b;">
                The project remains active and unchanged. Contact the portal administration if you need clarification.
            </p>
        </div>
        """
        next_plain = ("The project remains active and unchanged. "
                      "Contact the portal administration if you need clarification.")
        title, title_color, outcome_word = "Project Deletion Status Update", "#dc2626", "rejected"

    detail_rows = [("Project", safe_title)]
    if description:
        detail_rows.append(("Description", description))
    if required_skill:
        detail_rows.append(("Required Skill", required_skill))
    detail_rows.append(("Decision", outcome_word.capitalize()))
    detail_plain = "\n".join([f"{k}: {v}" for k, v in detail_rows])
    detail_html = "".join([
        f"""<div style="display: flex; gap: 8px; font-size: 13px; padding: 7px 0; border-bottom: 1px solid #f1f5f9;">
            <span style="min-width: 110px; color: #64748b; font-weight: 600;">{_esc(k)}</span>
            <span style="color: #0f172a; font-weight: 500;">{_esc(v)}</span>
        </div>""" for k, v in detail_rows
    ])

    plain_text = (
        f"{salutation}\n\n"
        f"{relevance}\n\n"
        f"{detail_plain}\n"
        f"{reviewed_by}\n\n"
        f"{next_plain}\n\n"
        f"A matching notification is also waiting in your Notification Hub.\n\n"
        f"Best regards,\n"
        f"Research Management Portal\n"
        f"United International University"
    )
    html_content = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 520px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff; color: #1e293b;">
        <div style="text-align: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid #e2e8f0;">
            <h1 style="color: #1e3a8a; margin: 0; font-size: 22px; font-weight: 700;">United International University</h1>
            <p style="color: #64748b; margin: 4px 0 0 0; font-size: 14px;">Research Management Portal</p>
        </div>
        <h2 style="color: {title_color}; margin: 0 0 16px 0; font-size: 20px;">{title}</h2>
        <p style="font-size: 15px; margin-bottom: 12px;">{salutation}</p>
        <p style="font-size: 14px; color: #334155; line-height: 1.6;">{relevance}</p>
        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px 16px; margin: 20px 0;">
            {detail_html}
            <div style="font-size: 12px; color: #64748b; padding: 7px 0;">{_esc(reviewed_by)}</div>
        </div>
        {next_box}
        <p style="font-size: 13px; color: #475569;">A matching notification is also waiting in your Notification Hub.</p>
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0 16px 0;">
        <p style="font-size: 12px; color: #94a3b8; text-align: center; margin: 0;">Sent by Research Management Portal to {to_email}</p>
        <p style="font-size: 11px; color: #94a3b8; text-align: center; margin: 8px 0 0 0;">United International University, Dhaka, Bangladesh</p>
    </div>
    """

    email_sent = False
    if sender_email and sender_password and mail_sending_enabled():
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"United International University Research Portal <{sender_email}>"
            msg["To"] = to_email
            msg["Reply-To"] = sender_email
            msg["Return-Path"] = sender_email
            msg["Date"] = formatdate(localtime=True)
            msg["Message-ID"] = make_msgid(domain=sender_email.split("@")[-1] if "@" in sender_email else "gmail.com")
            msg["X-Mailer"] = "ResearchPortalAuth/2.2"
            msg["MIME-Version"] = "1.0"
            msg["Precedence"] = "bulk"
            msg["List-Unsubscribe"] = f"<mailto:{sender_email}?subject=unsubscribe>, <https://uiu.ac.bd/unsubscribe>"
            msg["Auto-Submitted"] = "auto-generated"

            msg.attach(MIMEText(plain_text, "plain"))
            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, [to_email], msg.as_string())
            email_sent = True
        except Exception as e:
            print(f"[PROJECT OUTCOME EMAIL ERROR] Failed to send project {kind} {out} email to {to_email}: {e}")

    print(f"\n==================================================")
    print(f"[PROJECT OUTCOME EMAIL] Faculty {kind} request {out.upper()} for {to_email} (Project: {safe_title})")
    print(f"Status: {'Sent successfully via Gmail' if email_sent else 'Printed to console (Configure GMAIL_SENDER_EMAIL & GMAIL_APP_PASSWORD in .env for real Gmail delivery)'}")
    print(f"==================================================\n")
    return email_sent


def authenticate_user(db: Session, login_data: schemas.LoginRequest):
    query = text("SELECT user_id, email, password, role FROM user WHERE email = :email")
    result = db.execute(query, {"email": login_data.email}).fetchone()
    if result and verify_password(login_data.password, result.password):
        return {
            "user_id": result.user_id,
            "email": result.email,
            "role": result.role
        }
    return None

def get_admins(db: Session):
    query = text("SELECT user_id AS admin_id, email, role FROM user WHERE role = 'admin'")
    results = db.execute(query).fetchall()
    return [{"admin_id": r.admin_id, "email": r.email, "role": r.role} for r in results]

def get_admin_by_id(db: Session, admin_id: int):
    query = text("SELECT user_id AS admin_id, email, role FROM user WHERE user_id = :admin_id AND role = 'admin'")
    result = db.execute(query, {"admin_id": admin_id}).fetchone()
    if result:
        return {"admin_id": result.admin_id, "email": result.email, "role": result.role}
    return None

def create_admin(db: Session, admin: schemas.AdminCreate):
    check_query = text("SELECT user_id FROM user WHERE email = :email")
    existing = db.execute(check_query, {"email": admin.email}).fetchone()
    if existing:
        raise ValueError("Email already registered")

    insert_query = text("INSERT INTO user (email, password, role) VALUES (:email, :password, 'admin')")
    db.execute(insert_query, {"email": admin.email, "password": hash_password(admin.password)})
    db.commit()

    fetch_query = text("SELECT user_id AS admin_id, email, role FROM user WHERE email = :email")
    result = db.execute(fetch_query, {"email": admin.email}).fetchone()
    if result:
        _append_credentials_json(result.admin_id, result.email, "admin", admin.password)
    return {"admin_id": result.admin_id, "email": result.email, "role": result.role}

def update_admin(db: Session, admin_id: int, admin_update: schemas.AdminUpdate):
    admin_query = text("SELECT user_id, password FROM user WHERE user_id = :admin_id AND role = 'admin'")
    admin = db.execute(admin_query, {"admin_id": admin_id}).fetchone()
    if not admin:
        return None

    if not verify_password(admin_update.current_password, admin.password):
        raise ValueError("Incorrect current password")

    if admin_update.email:
        email_check = text("SELECT user_id FROM user WHERE email = :email AND user_id != :admin_id")
        existing_email = db.execute(email_check, {"email": admin_update.email, "admin_id": admin_id}).fetchone()
        if existing_email:
            raise ValueError("Email already in use")

    new_email = admin_update.email if admin_update.email else None
    new_password = hash_password(admin_update.new_password) if admin_update.new_password else None

    if new_email and new_password:
        update_q = text("UPDATE user SET email = :email, password = :password WHERE user_id = :admin_id")
        db.execute(update_q, {"email": new_email, "password": new_password, "admin_id": admin_id})
    elif new_email:
        update_q = text("UPDATE user SET email = :email WHERE user_id = :admin_id")
        db.execute(update_q, {"email": new_email, "admin_id": admin_id})
    elif new_password:
        update_q = text("UPDATE user SET password = :password WHERE user_id = :admin_id")
        db.execute(update_q, {"password": new_password, "admin_id": admin_id})

    db.commit()
    # DEV JSON SYNC: keep plain email+password in sync for easy login
    try:
        final_email = new_email or db.execute(
            text("SELECT email FROM user WHERE user_id = :admin_id"),
            {"admin_id": admin_id}).fetchone().email
        _append_credentials_json(
            admin_id, final_email, "admin",
            admin_update.new_password if admin_update.new_password else None)
    except Exception:
        pass
    return get_admin_by_id(db=db, admin_id=admin_id)

def delete_admin(db: Session, admin_id: int, current_password: str):
    admin_query = text("SELECT user_id, password FROM user WHERE user_id = :admin_id AND role = 'admin'")
    admin = db.execute(admin_query, {"admin_id": admin_id}).fetchone()
    if not admin:
        return False
    if not verify_password(current_password, admin.password):
        raise ValueError("Incorrect current password")

    delete_q = text("DELETE FROM user WHERE user_id = :admin_id")
    db.execute(delete_q, {"admin_id": admin_id})
    db.commit()
    try:
        _remove_credentials_json(admin_id)
    except Exception:
        pass
    return True

def get_faculties(db: Session, skip: int = 0, limit: int = 100):
    query = text("SELECT faculty_id, name, designation, department, office_hours FROM faculty LIMIT :limit OFFSET :skip")
    faculties = db.execute(query, {"limit": limit, "skip": skip}).fetchall()
    result = []
    for fac in faculties:
        user_q = text("SELECT email FROM user WHERE user_id = :faculty_id")
        user_res = db.execute(user_q, {"faculty_id": fac.faculty_id}).fetchone()
        email = user_res.email if user_res else ""

        area_q = text("SELECT research_area FROM faculty_research_areas WHERE faculty_id = :faculty_id")
        areas = db.execute(area_q, {"faculty_id": fac.faculty_id}).fetchall()
        research_areas = [{"faculty_id": fac.faculty_id, "research_area": a.research_area} for a in areas]

        result.append({
            "faculty_id": fac.faculty_id,
            "name": fac.name,
            "designation": fac.designation,
            "department": fac.department,
            "office_hours": fac.office_hours,
            "email": email,
            "research_areas": research_areas
        })
    return result

def get_faculty_by_id(db: Session, faculty_id: int):
    query = text("SELECT faculty_id, name, designation, department, office_hours FROM faculty WHERE faculty_id = :faculty_id")
    fac = db.execute(query, {"faculty_id": faculty_id}).fetchone()
    if not fac:
        return None
    user_q = text("SELECT email FROM user WHERE user_id = :faculty_id")
    user_res = db.execute(user_q, {"faculty_id": faculty_id}).fetchone()
    email = user_res.email if user_res else ""

    area_q = text("SELECT research_area FROM faculty_research_areas WHERE faculty_id = :faculty_id")
    areas = db.execute(area_q, {"faculty_id": faculty_id}).fetchall()
    research_areas = [{"faculty_id": faculty_id, "research_area": a.research_area} for a in areas]

    return {
        "faculty_id": fac.faculty_id,
        "name": fac.name,
        "designation": fac.designation,
        "department": fac.department,
        "office_hours": fac.office_hours,
        "email": email,
        "research_areas": research_areas
    }

def create_faculty(db: Session, faculty: schemas.FacultyCreate):
    check_q = text("SELECT user_id FROM user WHERE email = :email")
    if db.execute(check_q, {"email": faculty.email}).fetchone():
        raise ValueError("Email already registered")

    user_ins = text("INSERT INTO user (email, password, role) VALUES (:email, :password, 'Faculty')")
    db.execute(user_ins, {"email": faculty.email, "password": hash_password(faculty.password)})
    db.commit()

    user_sel = text("SELECT user_id FROM user WHERE email = :email")
    user_id = db.execute(user_sel, {"email": faculty.email}).fetchone().user_id

    fac_ins = text("INSERT INTO faculty (faculty_id, name, designation, department, office_hours) VALUES (:faculty_id, :name, :designation, :department, :office_hours)")
    db.execute(fac_ins, {
        "faculty_id": user_id,
        "name": faculty.name,
        "designation": faculty.designation,
        "department": faculty.department,
        "office_hours": faculty.office_hours
    })

    for area in faculty.research_areas:
        area_ins = text("INSERT INTO faculty_research_areas (faculty_id, research_area) VALUES (:faculty_id, :research_area)")
        db.execute(area_ins, {"faculty_id": user_id, "research_area": area})
    db.commit()
    _append_credentials_json(user_id, faculty.email, "Faculty", faculty.password)
    return get_faculty_by_id(db=db, faculty_id=user_id)

def update_faculty(db: Session, faculty_id: int, faculty_update: schemas.FacultyUpdate):
    user_q = text("SELECT password FROM user WHERE user_id = :faculty_id")
    user_res = db.execute(user_q, {"faculty_id": faculty_id}).fetchone()
    if not user_res:
        return None
    if not verify_password(faculty_update.current_password, user_res.password):
        raise ValueError("Incorrect current password")

    current_fac_q = text("SELECT name, designation FROM faculty WHERE faculty_id = :faculty_id")
    current_fac = db.execute(current_fac_q, {"faculty_id": faculty_id}).fetchone()

    if current_fac and faculty_update.designation and faculty_update.designation != current_fac.designation:
        payload = json.dumps({
            "message": f"Faculty '{current_fac.name}' requested a designation change from '{current_fac.designation}' to '{faculty_update.designation}'.",
            "new_designation": faculty_update.designation
        })
        notif_q = text("INSERT INTO notification (faculty_id, type, payload, status) VALUES (:faculty_id, 'DesignationChange', :payload, 'Pending')")
        db.execute(notif_q, {"faculty_id": faculty_id, "payload": payload})

    if faculty_update.name or faculty_update.department or faculty_update.office_hours:
        fac_q = text("""UPDATE faculty SET 
                        name = COALESCE(:name, name), 
                        department = COALESCE(:department, department), 
                        office_hours = COALESCE(:office_hours, office_hours) 
                        WHERE faculty_id = :faculty_id""")
        db.execute(fac_q, {
            "name": faculty_update.name,
            "department": faculty_update.department,
            "office_hours": faculty_update.office_hours,
            "faculty_id": faculty_id
        })

    if faculty_update.email:
        email_q = text("UPDATE user SET email = :email WHERE user_id = :faculty_id")
        db.execute(email_q, {"email": faculty_update.email, "faculty_id": faculty_id})

    if faculty_update.new_password:
        pass_q = text("UPDATE user SET password = :password WHERE user_id = :faculty_id")
        db.execute(pass_q, {"password": hash_password(faculty_update.new_password), "faculty_id": faculty_id})

    if faculty_update.research_areas is not None:
        del_areas = text("DELETE FROM faculty_research_areas WHERE faculty_id = :faculty_id")
        db.execute(del_areas, {"faculty_id": faculty_id})
        for area in faculty_update.research_areas:
            ins_area = text("INSERT INTO faculty_research_areas (faculty_id, research_area) VALUES (:faculty_id, :research_area)")
            db.execute(ins_area, {"faculty_id": faculty_id, "research_area": area})

    db.commit()
    # DEV JSON SYNC: email and/or password change -> update JSON
    try:
        cur_email_row = db.execute(
            text("SELECT email FROM user WHERE user_id = :fid"),
            {"fid": faculty_id}).fetchone()
        if cur_email_row:
            _append_credentials_json(
                faculty_id, cur_email_row.email, "Faculty",
                faculty_update.new_password if faculty_update.new_password else None)
    except Exception:
        pass
    return get_faculty_by_id(db=db, faculty_id=faculty_id)

def request_faculty_edit_by_admin(db: Session, faculty_id: int, edit: schemas.AdminFacultyEditRequest, actor_id=None):
    current = get_faculty_by_id(db=db, faculty_id=faculty_id)
    if not current:
        raise ValueError("Faculty not found")

    current_areas = sorted([a["research_area"] for a in current["research_areas"]])
    changes = {}

    if edit.name is not None and edit.name != current["name"]:
        changes["name"] = {"old": current["name"], "new": edit.name}
    if edit.email is not None and edit.email != current["email"]:
        changes["email"] = {"old": current["email"], "new": edit.email}
    if edit.designation is not None and edit.designation != current["designation"]:
        changes["designation"] = {"old": current["designation"], "new": edit.designation}
    if edit.department is not None and edit.department != current["department"]:
        changes["department"] = {"old": current["department"], "new": edit.department}
    if edit.office_hours is not None and edit.office_hours != current["office_hours"]:
        changes["office_hours"] = {"old": current["office_hours"], "new": edit.office_hours}
    if edit.research_areas is not None and sorted(edit.research_areas) != current_areas:
        changes["research_areas"] = {"old": current_areas, "new": edit.research_areas}

    if not changes:
        raise ValueError("No changes were detected to propose")

    payload = json.dumps({
        "message": f"The administration has proposed updates to your faculty profile.",
        "changes": changes
    })
    notif_q = text("INSERT INTO notification (faculty_id, type, payload, status) VALUES (:faculty_id, 'AdminFacultyEditRequest', :payload, 'Pending')")
    db.execute(notif_q, {"faculty_id": faculty_id, "payload": payload})
    db.commit()
    try:
        new_nid = db.execute(text("SELECT notification_id FROM notification WHERE faculty_id = :f AND type = 'AdminFacultyEditRequest' ORDER BY notification_id DESC LIMIT 1"), {"f": faculty_id}).fetchone()
        _log_admin_activity(db, actor_id, "propose_faculty_edit",
                            notification_id=int(new_nid.notification_id) if new_nid else None,
                            notification_type="AdminFacultyEditRequest",
                            detail=f"Proposed faculty profile edit for faculty {faculty_id}: " + "; ".join([f"{k}: {v.get('old')} → {v.get('new')}" for k, v in (changes or {}).items()]),
                            snapshot={"faculty_id": faculty_id, "changes": changes})
        db.commit()
    except Exception:
        pass
    return {"message": "Edit request sent to the faculty member for approval."}

def get_all_students(db: Session):
    _ensure_student_schema(db)
    students = db.execute(text("SELECT student_id, name, cgpa, department, semester, github_link, cv_link FROM student")).fetchall()
    result = []
    for s in students:
        user = db.execute(text("SELECT email FROM user WHERE user_id = :sid"), {"sid": s.student_id}).fetchone()
        skills = [r.skill for r in db.execute(text("SELECT skill FROM student_skills WHERE student_id = :sid"), {"sid": s.student_id}).fetchall()]
        interests = [r.research_area for r in db.execute(text("SELECT research_area FROM student_interests WHERE student_id = :sid"), {"sid": s.student_id}).fetchall()]
        result.append({
            "student_id": s.student_id,
            "name": s.name,
            "cgpa": str(s.cgpa) if s.cgpa is not None else None,
            "department": s.department,
            "semester": s.semester,
            "github_link": s.github_link,
            "cv_link": s.cv_link,
            "email": user.email if user else None,
            "skills": skills,
            "interests": interests
        })
    return result

def request_student_edit_by_admin(db: Session, student_id: int, edit: schemas.AdminStudentEditRequest, actor_id=None):
    current = get_student_by_id(db=db, student_id=student_id)
    if not current:
        raise ValueError("Student not found")
    
    changes = {}
    
    if edit.name is not None and edit.name != current["name"]:
        changes["name"] = {"old": current["name"], "new": edit.name}
    if edit.email is not None and edit.email != current["email"]:
        changes["email"] = {"old": current["email"], "new": edit.email}
    if edit.cgpa is not None and str(edit.cgpa) != str(current.get("cgpa") or ""):
        changes["cgpa"] = {"old": str(current.get("cgpa") or ""), "new": str(edit.cgpa)}
    if edit.department is not None and edit.department != current["department"]:
        changes["department"] = {"old": current["department"], "new": edit.department}
    if edit.semester is not None and edit.semester != current["semester"]:
        changes["semester"] = {"old": current["semester"], "new": edit.semester}
    if edit.github_link is not None and edit.github_link != current["github_link"]:
        changes["github_link"] = {"old": current["github_link"], "new": edit.github_link}
    if edit.cv_link is not None and edit.cv_link != current["cv_link"]:
        changes["cv_link"] = {"old": current["cv_link"], "new": edit.cv_link}
    if edit.skills is not None and sorted(edit.skills) != sorted(current.get("skills") or []):
        changes["skills"] = {"old": current.get("skills") or [], "new": edit.skills}
    if edit.interests is not None and sorted(edit.interests) != sorted(current.get("interests") or []):
        changes["interests"] = {"old": current.get("interests") or [], "new": edit.interests}
    
    if not changes:
        raise ValueError("No changes were detected to propose")
    
    payload = json.dumps({
        "message": f"The administration has proposed updates to your student profile.",
        "changes": changes
    })
    notif_q = text("INSERT INTO notification (faculty_id, student_id, type, payload, status) VALUES (NULL, :sid, 'AdminStudentEditRequest', :payload, 'Pending')")
    db.execute(notif_q, {"sid": student_id, "payload": payload})
    db.commit()
    try:
        new_nid = db.execute(text("SELECT notification_id FROM notification WHERE student_id = :s AND type = 'AdminStudentEditRequest' ORDER BY notification_id DESC LIMIT 1"), {"s": student_id}).fetchone()
        _log_admin_activity(db, actor_id, "propose_student_edit",
                            notification_id=int(new_nid.notification_id) if new_nid else None,
                            notification_type="AdminStudentEditRequest",
                            detail=f"Proposed student profile edit for student {student_id}: " + "; ".join([f"{k}: {v.get('old')} → {v.get('new')}" for k, v in (changes or {}).items()]),
                            snapshot={"student_id": student_id, "changes": changes})
        db.commit()
    except Exception:
        pass
    return {"message": "Edit request sent to the student for approval."}

def handle_faculty_notification_response(db: Session, notification_id: int, faculty_id: int, action: str):
    notif_q = text("SELECT notification_id, faculty_id, type, payload, status FROM notification WHERE notification_id = :notification_id")
    notif = db.execute(notif_q, {"notification_id": notification_id}).fetchone()
    if not notif:
        raise ValueError("Notification not found")
    if notif.faculty_id != faculty_id:
        raise ValueError("This notification does not belong to you")
    if notif.type not in (
        "AdminFacultyEditRequest",
        "DesignationChange",
        "ProjectCreation",
        "ProjectCreationResult",
        "ProjectDeletionResult",
        "AccountDeletionResult",
        "DesignationChangeResult",
        "ProjectApplication",
        "SuperAdminProjectUpdate",
    ):
        raise ValueError("This notification cannot be responded to here")

    new_status = "Accepted" if action.lower().startswith("accept") else "Rejected"

    if notif.type in ("ProjectCreationResult", "ProjectDeletionResult", "AccountDeletionResult", "DesignationChangeResult", "ProjectApplication", "SuperAdminProjectUpdate"):
        if notif.status != "Pending":
            raise ValueError("This notification has already been acknowledged")
        up_q = text("UPDATE notification SET status = 'Accepted' WHERE notification_id = :notification_id")
        db.execute(up_q, {"notification_id": notification_id})
        db.commit()
        return {"message": "Notification acknowledged"}

    if notif.type == "AdminFacultyEditRequest":
        if notif.status != "Pending":
            raise ValueError("This notification has already been handled")

        if new_status == "Accepted":
            try:
                payload_data = json.loads(notif.payload)
                changes = payload_data.get("changes", {})
            except (ValueError, TypeError):
                changes = {}

            field_map = {
                "name": "name",
                "designation": "designation",
                "department": "department",
                "office_hours": "office_hours"
            }
            for field, column in field_map.items():
                if field in changes:
                    upd_q = text(f"UPDATE faculty SET {column} = :value WHERE faculty_id = :faculty_id")
                    db.execute(upd_q, {"value": changes[field]["new"], "faculty_id": faculty_id})

            if "email" in changes:
                email_q = text("UPDATE user SET email = :email WHERE user_id = :faculty_id")
                db.execute(email_q, {"email": changes["email"]["new"], "faculty_id": faculty_id})
                try:
                    _sync_credentials_email_only(faculty_id, changes["email"]["new"], "Faculty")
                except Exception:
                    pass

            if "research_areas" in changes:
                del_areas = text("DELETE FROM faculty_research_areas WHERE faculty_id = :faculty_id")
                db.execute(del_areas, {"faculty_id": faculty_id})
                for area in changes["research_areas"]["new"]:
                    ins_area = text("INSERT INTO faculty_research_areas (faculty_id, research_area) VALUES (:faculty_id, :research_area)")
                    db.execute(ins_area, {"faculty_id": faculty_id, "research_area": area})

    elif notif.type == "DesignationChange":
        if notif.status != "AwaitingFacultyConfirmation":
            raise ValueError("This request is not currently awaiting your confirmation")

        if new_status == "Accepted":
            try:
                payload_data = json.loads(notif.payload)
                new_designation = payload_data.get("new_designation")
            except (ValueError, TypeError):
                new_designation = None
            if new_designation:
                upd_q = text("UPDATE faculty SET designation = :designation WHERE faculty_id = :faculty_id")
                db.execute(upd_q, {"designation": new_designation, "faculty_id": faculty_id})

    elif notif.type == "ProjectCreation":
        if notif.status != "AwaitingFacultyConfirmation":
            raise ValueError("This request is not currently awaiting your confirmation")

        if new_status == "Accepted":
            try:
                payload_data = json.loads(notif.payload)
            except (ValueError, TypeError):
                payload_data = {}
            ins_q = text("""INSERT INTO research_project (faculty_id, title, description, required_skill, status) 
                            VALUES (:faculty_id, :title, :description, :required_skill, :status)""")
            db.execute(ins_q, {
                "faculty_id": payload_data.get("faculty_id", faculty_id),
                "title": payload_data.get("title"),
                "description": payload_data.get("description"),
                "required_skill": payload_data.get("required_skill"),
                "status": payload_data.get("status") or "Active"
            })

    up_q = text("UPDATE notification SET status = :status WHERE notification_id = :notification_id")
    db.execute(up_q, {"status": new_status, "notification_id": notification_id})
    db.commit()
    # Tell the originating admin (and only them) how the faculty responded.
    try:
        if notif.type in ("AdminFacultyEditRequest", "DesignationChange", "ProjectCreation"):
            try:
                _pd = json.loads(notif.payload)
                if not isinstance(_pd, dict):
                    _pd = {}
            except Exception:
                _pd = {}
            if notif.type == "AdminFacultyEditRequest":
                _summary = "; ".join([f"{k}: {v.get('old')} → {v.get('new')}"
                                      for k, v in ((_pd.get("changes") or {}).items())]) or "Profile update proposal"
            elif notif.type == "DesignationChange":
                _summary = f"Designation → {_pd.get('new_designation') or '—'}"
            else:
                _summary = f"Project '{_pd.get('title') or '—'}' creation"
            try:
                _fn, _fe = _faculty_contact(db, faculty_id)
            except Exception:
                _fn = None
            _email_response_to_originator(
                db, notification_id, notif.type,
                f"Faculty {_fn or faculty_id}", new_status, _summary)
    except Exception:
        pass
    return {"message": f"Notification {new_status}"}

def delete_faculty(db: Session, faculty_id: int):
    q = text("SELECT user_id FROM user WHERE user_id = :faculty_id")
    if not db.execute(q, {"faculty_id": faculty_id}).fetchone():
        return False
    try:
        _del_name, _del_email = _faculty_contact(db, faculty_id)
    except Exception:
        _del_name, _del_email = None, ""
    del_q = text("DELETE FROM user WHERE user_id = :faculty_id")
    db.execute(del_q, {"faculty_id": faculty_id})
    db.commit()
    try:
        if _del_email:
            try:
                send_info_email(
                    _del_email, "Your portal account was removed",
                    f"Your Research Management Portal faculty account"
                    f"{(' (' + _del_name + ')') if _del_name else ''} was removed by the administration "
                    f"along with all related data. Contact administration if you believe this is a mistake.")
            except Exception:
                pass
    except Exception:
        pass
    try:
        _remove_credentials_json(faculty_id)
    except Exception:
        pass
    return True

def request_delete_faculty(db: Session, faculty_id: int, current_password: str):
    user_q = text("SELECT password FROM user WHERE user_id = :faculty_id")
    user_res = db.execute(user_q, {"faculty_id": faculty_id}).fetchone()
    if not user_res:
        raise ValueError("Faculty not found")
    if not verify_password(current_password, user_res.password):
        raise ValueError("Incorrect current password")

    fac_q = text("SELECT name FROM faculty WHERE faculty_id = :faculty_id")
    fac = db.execute(fac_q, {"faculty_id": faculty_id}).fetchone()
    fac_name = fac.name if fac else "Unknown"

    payload = json.dumps({
        "message": f"Faculty '{fac_name}' has requested permanent deletion of their account."
    })
    notif_q = text("INSERT INTO notification (faculty_id, type, payload, status) VALUES (:faculty_id, 'AccountDeletion', :payload, 'Pending')")
    db.execute(notif_q, {"faculty_id": faculty_id, "payload": payload})
    db.commit()
    return {"message": "Deletion request submitted. Awaiting admin approval."}

def get_projects(db: Session, skip: int = 0, limit: int = 100):
    query = text("SELECT project_id, faculty_id, title, description, required_skill, status FROM research_project LIMIT :limit OFFSET :skip")
    projects = db.execute(query, {"limit": limit, "skip": skip}).fetchall()
    result = []
    for p in projects:
        fac_q = text("SELECT name, department FROM faculty WHERE faculty_id = :faculty_id")
        fac = db.execute(fac_q, {"faculty_id": p.faculty_id}).fetchone()
        result.append({
            "project_id": p.project_id,
            "faculty_id": p.faculty_id,
            "title": p.title,
            "description": p.description,
            "required_skill": p.required_skill,
            "status": p.status,
            "faculty_name": fac.name if fac else None,
            "department": fac.department if fac else None
        })
    return result

def get_projects_by_faculty(db: Session, faculty_id: int):
    query = text("SELECT project_id, faculty_id, title, description, required_skill, status FROM research_project WHERE faculty_id = :faculty_id")
    projects = db.execute(query, {"faculty_id": faculty_id}).fetchall()
    result = []
    fac_q = text("SELECT name, department FROM faculty WHERE faculty_id = :faculty_id")
    fac = db.execute(fac_q, {"faculty_id": faculty_id}).fetchone()
    for p in projects:
        result.append({
            "project_id": p.project_id,
            "faculty_id": p.faculty_id,
            "title": p.title,
            "description": p.description,
            "required_skill": p.required_skill,
            "status": p.status,
            "faculty_name": fac.name if fac else None,
            "department": fac.department if fac else None
        })
    return result

def get_project_by_id(db: Session, project_id: int):
    query = text("SELECT project_id, faculty_id, title, description, required_skill, status FROM research_project WHERE project_id = :project_id")
    p = db.execute(query, {"project_id": project_id}).fetchone()
    if not p:
        return None
    fac_q = text("SELECT name, department FROM faculty WHERE faculty_id = :faculty_id")
    fac = db.execute(fac_q, {"faculty_id": p.faculty_id}).fetchone()
    return {
        "project_id": p.project_id,
        "faculty_id": p.faculty_id,
        "title": p.title,
        "description": p.description,
        "required_skill": p.required_skill,
        "status": p.status,
        "faculty_name": fac.name if fac else None,
        "department": fac.department if fac else None
    }

def create_project(db: Session, project: schemas.ResearchProjectCreate):
    user_q = text("SELECT password FROM user WHERE user_id = :faculty_id")
    user = db.execute(user_q, {"faculty_id": project.faculty_id}).fetchone()
    if not user or not verify_password(project.current_password, user.password):
        raise ValueError("Incorrect current password")

    ins_q = text("""INSERT INTO research_project (faculty_id, title, description, required_skill, status) 
                    VALUES (:faculty_id, :title, :description, :required_skill, :status)""")
    db.execute(ins_q, {
        "faculty_id": project.faculty_id,
        "title": project.title,
        "description": project.description,
        "required_skill": project.required_skill,
        "status": project.status
    })
    db.commit()
    sel_q = text("SELECT project_id FROM research_project WHERE faculty_id = :faculty_id ORDER BY project_id DESC LIMIT 1")
    new_id = db.execute(sel_q, {"faculty_id": project.faculty_id}).fetchone().project_id
    return get_project_by_id(db=db, project_id=new_id)

def request_project_creation(db: Session, project: schemas.ResearchProjectCreate):
    user_q = text("SELECT password FROM user WHERE user_id = :faculty_id")
    user = db.execute(user_q, {"faculty_id": project.faculty_id}).fetchone()
    if not user or not verify_password(project.current_password, user.password):
        raise ValueError("Incorrect current password")

    fac_q = text("SELECT name FROM faculty WHERE faculty_id = :faculty_id")
    fac = db.execute(fac_q, {"faculty_id": project.faculty_id}).fetchone()
    fac_name = fac.name if fac else "Unknown"

    payload = json.dumps({
        "message": f"Faculty '{fac_name}' has requested to create a new research project titled '{project.title}'.",
        "faculty_id": project.faculty_id,
        "title": project.title,
        "description": project.description,
        "required_skill": project.required_skill,
        "status": project.status
    })
    notif_q = text("INSERT INTO notification (faculty_id, type, payload, status) VALUES (:faculty_id, 'ProjectCreation', :payload, 'Pending')")
    db.execute(notif_q, {"faculty_id": project.faculty_id, "payload": payload})
    db.commit()
    return {"message": "Project creation request submitted. Awaiting admin approval."}

def update_project(db: Session, project_id: int, project_update: schemas.ResearchProjectUpdate, faculty_id: int):
    proj_q = text("SELECT faculty_id FROM research_project WHERE project_id = :project_id")
    proj = db.execute(proj_q, {"project_id": project_id}).fetchone()
    if not proj:
        return None
    if proj.faculty_id != faculty_id:
        raise ValueError("Unauthorized to update this project")

    user_q = text("SELECT password FROM user WHERE user_id = :faculty_id")
    user = db.execute(user_q, {"faculty_id": faculty_id}).fetchone()
    if not user or not verify_password(project_update.current_password, user.password):
        raise ValueError("Incorrect current password")

    up_q = text("""UPDATE research_project SET 
                   title = COALESCE(:title, title), 
                   description = COALESCE(:description, description), 
                   required_skill = COALESCE(:required_skill, required_skill), 
                   status = COALESCE(:status, status) 
                   WHERE project_id = :project_id""")
    db.execute(up_q, {
        "title": project_update.title,
        "description": project_update.description,
        "required_skill": project_update.required_skill,
        "status": project_update.status,
        "project_id": project_id
    })
    db.commit()
    return get_project_by_id(db=db, project_id=project_id)

def delete_project(db: Session, project_id: int, faculty_id: int, current_password: str):
    proj_q = text("SELECT faculty_id, title FROM research_project WHERE project_id = :project_id")
    proj = db.execute(proj_q, {"project_id": project_id}).fetchone()
    if not proj:
        return None
    if proj.faculty_id != faculty_id:
        raise ValueError("Unauthorized to delete this project")

    user_q = text("SELECT password FROM user WHERE user_id = :faculty_id")
    user = db.execute(user_q, {"faculty_id": faculty_id}).fetchone()
    if not user or not verify_password(current_password, user.password):
        raise ValueError("Incorrect current password")

    fac_q = text("SELECT name FROM faculty WHERE faculty_id = :faculty_id")
    fac = db.execute(fac_q, {"faculty_id": faculty_id}).fetchone()
    fac_name = fac.name if fac else "Unknown"

    payload = json.dumps({
        "message": f"Faculty '{fac_name}' has requested to delete the project '{proj.title}'.",
        "project_id": project_id,
        "title": proj.title
    })
    notif_q = text("INSERT INTO notification (faculty_id, type, payload, status) VALUES (:faculty_id, 'ProjectDeletion', :payload, 'Pending')")
    db.execute(notif_q, {"faculty_id": faculty_id, "payload": payload})
    db.commit()
    return {"message": "Project deletion request submitted. Awaiting admin approval."}

def _populate_application_student_details(db: Session, app_data: dict):
    stu_name = app_data.get("applicant_name")
    stu_cgpa = app_data.get("applicant_cgpa")
    stu_dept = app_data.get("applicant_department")
    stu_sem = app_data.get("applicant_semester")
    stu_gh = app_data.get("applicant_github")
    stu_cv = app_data.get("applicant_cv")
    stu_skills = app_data.get("applicant_skills")
    stu_interests = app_data.get("applicant_interests")

    need_fallback = (
        not stu_name or stu_name == 'Not Applicable' or
        not stu_cgpa or stu_cgpa == 'Not Applicable' or
        not stu_dept or stu_dept == 'Not Applicable' or
        not stu_sem or stu_sem == 'Not Applicable'
    )
    if need_fallback and app_data.get("student_id"):
        try:
            stu = db.execute(
                text("SELECT name, cgpa, department, semester, github_link, cv_link FROM student WHERE student_id = :sid"),
                {"sid": app_data["student_id"]}
            ).fetchone()
            if stu:
                sd = dict(stu._mapping) if hasattr(stu, '_mapping') else stu._asdict() if hasattr(stu, '_asdict') else {}
                if not stu_name or stu_name == 'Not Applicable': stu_name = sd.get("name")
                if not stu_cgpa or stu_cgpa == 'Not Applicable': stu_cgpa = str(sd.get("cgpa")) if sd.get("cgpa") is not None else None
                if not stu_dept or stu_dept == 'Not Applicable': stu_dept = sd.get("department")
                if not stu_sem or stu_sem == 'Not Applicable': stu_sem = sd.get("semester")
                if not stu_gh or stu_gh == 'Not Applicable': stu_gh = sd.get("github_link")
                if not stu_cv or stu_cv == 'Not Applicable': stu_cv = sd.get("cv_link")
        except Exception:
            pass

    app_data["applicant_name"] = stu_name
    app_data["applicant_cgpa"] = stu_cgpa
    app_data["applicant_department"] = stu_dept
    app_data["applicant_semester"] = stu_sem
    app_data["applicant_github"] = stu_gh
    app_data["applicant_cv"] = stu_cv
    app_data["applicant_skills"] = stu_skills
    app_data["applicant_interests"] = stu_interests
    return app_data

def _build_application_item(db: Session, app_row, proj_title=None, faculty_name=None, dept=None):
    """Build application response item with current student data from student table."""
    d = dict(app_row._mapping) if hasattr(app_row, '_mapping') else app_row._asdict() if hasattr(app_row, '_asdict') else {}
    student_id = d.get("student_id")
    
    # Fetch current student data from student table
    current_student = None
    current_skills = []
    current_interests = []
    if student_id:
        try:
            stu = db.execute(text("SELECT name, cgpa, department, semester, github_link, cv_link FROM student WHERE student_id = :sid"), {"sid": student_id}).fetchone()
            if stu:
                current_student = dict(stu._mapping) if hasattr(stu, '_mapping') else stu._asdict() if hasattr(stu, '_asdict') else {}
            # Fetch current skills
            skills_rows = db.execute(text("SELECT skill FROM student_skills WHERE student_id = :sid"), {"sid": student_id}).fetchall()
            current_skills = [r.skill if hasattr(r, 'skill') else r[0] for r in skills_rows]
            # Fetch current interests
            interests_rows = db.execute(text("SELECT research_area FROM student_interests WHERE student_id = :sid"), {"sid": student_id}).fetchall()
            current_interests = [r.research_area if hasattr(r, 'research_area') else r[0] for r in interests_rows]
        except Exception:
            pass
    
    # Use current student data, fall back to application snapshot if not available
    applicant_name = current_student.get("name") if current_student else d.get("applicant_name")
    applicant_cgpa = str(current_student.get("cgpa")) if current_student and current_student.get("cgpa") is not None else d.get("applicant_cgpa")
    applicant_department = current_student.get("department") if current_student else d.get("applicant_department")
    applicant_semester = current_student.get("semester") if current_student else d.get("applicant_semester")
    applicant_github = current_student.get("github_link") if current_student else d.get("applicant_github")
    applicant_cv = current_student.get("cv_link") if current_student else d.get("applicant_cv")
    applicant_skills = current_skills if current_skills else (d.get("applicant_skills").split(",") if isinstance(d.get("applicant_skills"), str) and d.get("applicant_skills") else d.get("applicant_skills"))
    applicant_interests = current_interests if current_interests else (d.get("applicant_interests").split(",") if isinstance(d.get("applicant_interests"), str) and d.get("applicant_interests") else d.get("applicant_interests"))
    
    return {
        "project_id": d.get("project_id"),
        "application_id": d.get("application_id"),
        "student_id": d.get("student_id"),
        "cover_letter": d.get("cover_letter"),
        "status": d.get("status"),
        "project_title": proj_title,
        "faculty_name": faculty_name,
        "department": dept,
        "applicant_name": applicant_name,
        "applicant_cgpa": applicant_cgpa,
        "applicant_department": applicant_department,
        "applicant_semester": applicant_semester,
        "applicant_github": applicant_github,
        "applicant_cv": applicant_cv,
        "applicant_skills": applicant_skills,
        "applicant_interests": applicant_interests,
        "motivation": d.get("motivation"),
        "feedback": d.get("feedback"),
    }


def get_all_applications(db: Session):
    cols = _student_columns(db)
    sel = "project_id, application_id, student_id, cover_letter, status"
    for c in ["applicant_name", "applicant_cgpa", "applicant_department", "applicant_semester", "applicant_github", "applicant_cv", "applicant_skills", "applicant_interests", "motivation", "feedback"]:
        if c in cols: sel += f", {c}"
    query = text(f"SELECT {sel} FROM application")
    apps = db.execute(query).fetchall()
    result = []
    for app in apps:
        proj_q = text("SELECT title, faculty_id FROM research_project WHERE project_id = :project_id")
        proj = db.execute(proj_q, {"project_id": app.project_id}).fetchone()
        fac_name, dept = None, None
        if proj:
            fac_q = text("SELECT name, department FROM faculty WHERE faculty_id = :faculty_id")
            fac = db.execute(fac_q, {"faculty_id": proj.faculty_id}).fetchone()
            if fac:
                fac_name, dept = fac.name, fac.department
        item = _build_application_item(db, app, proj.title if proj else None, fac_name, dept)
        result.append(item)
    return result

def get_applications_for_project(db: Session, project_id: int):
    cols = _student_columns(db)
    sel = "project_id, application_id, student_id, cover_letter, status"
    for c in ["applicant_name", "applicant_cgpa", "applicant_department", "applicant_semester", "applicant_github", "applicant_cv", "applicant_skills", "applicant_interests", "motivation", "feedback"]:
        if c in cols: sel += f", {c}"
    query = text(f"SELECT {sel} FROM application WHERE project_id = :project_id")
    apps = db.execute(query, {"project_id": project_id}).fetchall()
    result = []
    proj_q = text("SELECT title, faculty_id FROM research_project WHERE project_id = :project_id")
    proj = db.execute(proj_q, {"project_id": project_id}).fetchone()
    fac_name, dept = None, None
    if proj:
        fac_q = text("SELECT name, department FROM faculty WHERE faculty_id = :faculty_id")
        fac = db.execute(fac_q, {"faculty_id": proj.faculty_id}).fetchone()
        if fac:
            fac_name, dept = fac.name, fac.department
    for app in apps:
        item = _build_application_item(db, app, proj.title if proj else None, fac_name, dept)
        result.append(item)
    return result

def get_applications_for_faculty(db: Session, faculty_id: int):
    proj_q = text("SELECT project_id FROM research_project WHERE faculty_id = :faculty_id")
    projects = db.execute(proj_q, {"faculty_id": faculty_id}).fetchall()
    proj_ids = [p.project_id for p in projects]
    if not proj_ids:
        return []

    result = []
    fac_q = text("SELECT name, department FROM faculty WHERE faculty_id = :faculty_id")
    fac = db.execute(fac_q, {"faculty_id": faculty_id}).fetchone()
    fac_name = fac.name if fac else None
    dept = fac.department if fac else None

    cols = _student_columns(db)
    sel = "project_id, application_id, student_id, cover_letter, status"
    for c in ["applicant_name", "applicant_cgpa", "applicant_department", "applicant_semester", "applicant_github", "applicant_cv", "applicant_skills", "applicant_interests", "motivation", "feedback"]:
        if c in cols: sel += f", {c}"

    for pid in proj_ids:
        p_q = text("SELECT title FROM research_project WHERE project_id = :pid")
        title_res = db.execute(p_q, {"pid": pid}).fetchone()
        title = title_res.title if title_res else None

        app_q = text(f"SELECT {sel} FROM application WHERE project_id = :pid")
        apps = db.execute(app_q, {"pid": pid}).fetchall()
        for app in apps:
            item = _build_application_item(db, app, title, fac_name, dept)
            result.append(item)
    return result

def update_application_status(db: Session, project_id: int, application_id: int, status_update: schemas.ApplicationStatusUpdate):
    cur = db.execute(text("SELECT status, student_id FROM application WHERE project_id = :pid AND application_id = :aid"), {"pid": project_id, "aid": application_id}).fetchone()
    if not cur:
        return None
    target = (status_update.status or "").capitalize()
    if target not in ("Approved", "Rejected", "Pending"):
        raise ValueError("Invalid status")
    if str(cur.status) == target:
        raise ValueError(f"Already {target.lower()}")
    if str(cur.status) in ("Approved", "Rejected"):
        raise ValueError("Decision finalized — cannot change")
    fb = getattr(status_update, "feedback", None)
    cols = _student_columns(db)
    if "feedback" in cols:
        db.execute(text("UPDATE application SET status = :s, feedback = :f WHERE project_id = :pid AND application_id = :aid"), {"s": target, "f": fb, "pid": project_id, "aid": application_id})
    else:
        db.execute(text("UPDATE application SET status = :s WHERE project_id = :pid AND application_id = :aid"), {"s": target, "pid": project_id, "aid": application_id})
    db.commit()
    # notify student (idempotent per decision)
    try:
        sid = int(cur.student_id)
        pj = db.execute(text("SELECT title, faculty_id FROM research_project WHERE project_id = :pid"), {"pid": project_id}).fetchone()
        pj_title = pj.title if pj and getattr(pj, "title", None) else None
        payload = json.dumps({"message": f"Your application for '{pj_title if pj_title else project_id}' has been {target.lower()}.", "project_id": project_id, "application_id": application_id, "project_title": pj_title, "outcome": target.lower(), "feedback": fb})
        try:
            db.execute(text("INSERT INTO notification (faculty_id, student_id, type, payload, status) VALUES (NULL, :sid, 'ApplicationDecision', :p, 'Pending')"), {"sid": sid, "p": payload})
        except Exception:
            db.rollback()
        db.commit()
        # email student on final decisions (Approved/Rejected only, not Pending)
        if target in ("Approved", "Rejected"):
            try:
                em = db.execute(text("SELECT email FROM user WHERE user_id = :sid"), {"sid": sid}).fetchone()
                st_row = db.execute(text("SELECT name FROM student WHERE student_id = :sid"), {"sid": sid}).fetchone()
                student_name = st_row.name if st_row and getattr(st_row, "name", None) else None
                fac_name = None
                if pj and getattr(pj, "faculty_id", None):
                    fac_row = db.execute(text("SELECT name FROM faculty WHERE faculty_id = :fid"), {"fid": pj.faculty_id}).fetchone()
                    fac_name = fac_row.name if fac_row and getattr(fac_row, "name", None) else None
                if em and getattr(em, "email", None):
                    send_application_decision_email(
                        to_email=em.email,
                        decision=target,
                        project_title=pj_title,
                        faculty_name=fac_name,
                        feedback=fb,
                        student_name=student_name,
                    )
            except Exception:
                pass
    except Exception:
        pass

    cols = _student_columns(db)
    sel = "project_id, application_id, student_id, cover_letter, status"
    for c in ["applicant_name", "applicant_cgpa", "applicant_department", "applicant_semester", "applicant_github", "applicant_cv", "applicant_skills", "applicant_interests", "motivation", "feedback"]:
        if c in cols: sel += f", {c}"

    app_q = text(f"SELECT {sel} FROM application WHERE project_id = :project_id AND application_id = :application_id")
    app = db.execute(app_q, {"project_id": project_id, "application_id": application_id}).fetchone()
    if not app:
        return None

    proj_q = text("SELECT title, faculty_id FROM research_project WHERE project_id = :project_id")
    proj = db.execute(proj_q, {"project_id": project_id}).fetchone()
    fac_name, dept = None, None
    if proj:
        fac_q = text("SELECT name, department FROM faculty WHERE faculty_id = :faculty_id")
        fac = db.execute(fac_q, {"faculty_id": proj.faculty_id}).fetchone()
        if fac:
            fac_name, dept = fac.name, fac.department

    d = dict(app._mapping) if hasattr(app, '_mapping') else app._asdict() if hasattr(app, '_asdict') else {}
    item = _build_application_item(db, app, proj.title if proj else None, fac_name, dept)
    return item

def get_department_project_summary(db: Session):
    query = text("""
        SELECT 
            f.department,
            COUNT(DISTINCT f.faculty_id) AS faculty_count,
            COUNT(rp.project_id) AS total_projects
        FROM faculty f
        LEFT JOIN research_project rp ON f.faculty_id = rp.faculty_id
        GROUP BY f.department
    """)
    res = db.execute(query).fetchall()
    return [{"department": r.department, "faculty_count": r.faculty_count, "total_projects": r.total_projects} for r in res]

def get_projects_above_average_applications(db: Session):
    query = text("""
        SELECT 
            rp.project_id,
            rp.title,
            rp.status,
            rp.applicant_count,
            rp.required_skill,
            f.name AS faculty_name,
            f.department
        FROM research_project rp
        JOIN faculty f ON rp.faculty_id = f.faculty_id
        WHERE rp.applicant_count > (SELECT AVG(applicant_count) FROM research_project WHERE status = 'Active')
    """)
    res = db.execute(query).fetchall()
    return [
        {
            "project_id": r.project_id,
            "title": r.title,
            "status": r.status,
            "applicant_count": r.applicant_count,
            "required_skill": r.required_skill,
            "faculty_name": r.faculty_name,
            "department": r.department
        }
        for r in res
    ]

def get_active_projects_from_view(db: Session):
    query = text("""
        SELECT 
            apv.project_id,
            apv.title,
            apv.status,
            rp.required_skill,
            f.name AS faculty_name,
            f.department,
            rp.applicant_count
        FROM active_projects_view apv
        JOIN research_project rp ON apv.project_id = rp.project_id
        JOIN faculty f ON rp.faculty_id = f.faculty_id
        WHERE apv.status = 'Active'
    """)
    res = db.execute(query).fetchall()
    return [
        {
            "project_id": r.project_id,
            "title": r.title,
            "status": r.status,
            "required_skill": r.required_skill,
            "faculty_name": r.faculty_name,
            "department": r.department,
            "applicant_count": r.applicant_count
        }
        for r in res
    ]

def get_all_departments(db: Session):
    query = text("SELECT DISTINCT department FROM faculty WHERE department IS NOT NULL ORDER BY department")
    res = db.execute(query).fetchall()
    return [r.department for r in res]

def get_department_summary_detail(db: Session, department: str):
    # Get running projects count and faculty count for the department
    summary_query = text("""
        SELECT 
            COUNT(DISTINCT f.faculty_id) AS faculty_count,
            COUNT(rp.project_id) AS total_projects,
            COUNT(CASE WHEN rp.status = 'Active' THEN 1 END) AS running_projects_count
        FROM faculty f
        LEFT JOIN research_project rp ON f.faculty_id = rp.faculty_id
        WHERE f.department = :department
    """)
    summary = db.execute(summary_query, {"department": department}).fetchone()
    
    # Get running projects list for the department
    projects_query = text("""
        SELECT 
            rp.project_id,
            rp.title,
            rp.status,
            rp.required_skill,
            rp.applicant_count,
            f.name AS faculty_name
        FROM research_project rp
        JOIN faculty f ON rp.faculty_id = f.faculty_id
        WHERE f.department = :department AND rp.status = 'Active'
    """)
    projects = db.execute(projects_query, {"department": department}).fetchall()
    
    running_projects = [
        {
            "project_id": r.project_id,
            "title": r.title,
            "status": r.status,
            "required_skill": r.required_skill,
            "applicant_count": r.applicant_count,
            "faculty_name": r.faculty_name
        }
        for r in projects
    ]
    
    return {
        "department": department,
        "faculty_count": summary.faculty_count if summary else 0,
        "total_projects": summary.total_projects if summary else 0,
        "running_projects_count": summary.running_projects_count if summary else 0,
        "running_projects": running_projects
    }

def get_popular_projects_overall(db: Session):
    # Correct math: average = total applications / total running projects.
    # (Never AVG() over a LEFT JOIN — that repeats each project once per
    # application row and inflates the benchmark.)
    stats_query = text("""
        SELECT
            COUNT(DISTINCT rp.project_id) AS total_running_projects,
            COUNT(a.project_id) AS total_applications
        FROM research_project rp
        LEFT JOIN application a ON rp.project_id = a.project_id
        WHERE rp.status = 'Active'
    """)
    overall = db.execute(stats_query).fetchone()

    total_running = int(overall.total_running_projects or 0) if overall else 0
    total_apps = int(overall.total_applications or 0) if overall else 0
    avg_apps = round(total_apps / total_running, 1) if total_running > 0 else 0.0
    
    # Get projects above average
    pop_query = text("""
        SELECT 
            rp.project_id,
            rp.title,
            rp.status,
            rp.required_skill,
            rp.applicant_count,
            f.name AS faculty_name,
            f.department
        FROM research_project rp
        JOIN faculty f ON rp.faculty_id = f.faculty_id
        WHERE rp.status = 'Active' AND rp.applicant_count > :avg_apps
        ORDER BY rp.applicant_count DESC
    """)
    pop_projects = db.execute(pop_query, {"avg_apps": avg_apps}).fetchall()
    
    popular_projects = [
        {
            "project_id": r.project_id,
            "title": r.title,
            "status": r.status,
            "required_skill": r.required_skill,
            "applicant_count": r.applicant_count,
            "faculty_name": r.faculty_name,
            "department": r.department
        }
        for r in pop_projects
    ]
    
    return {
        "total_running_projects": total_running,
        "total_applications": total_apps,
        "average_benchmark": round(avg_apps, 1),
        "popular_projects": popular_projects
    }

def get_popular_projects_by_department(db: Session, department: str):
    # Correct math: average = dept applications / dept running projects.
    # (Never AVG() over a LEFT JOIN — that repeats each project once per
    # application row and inflates the benchmark.)
    dept_query = text("""
        SELECT
            COUNT(DISTINCT rp.project_id) AS total_running_projects,
            COUNT(a.project_id) AS total_applications
        FROM research_project rp
        JOIN faculty f ON rp.faculty_id = f.faculty_id
        LEFT JOIN application a ON rp.project_id = a.project_id
        WHERE f.department = :department AND rp.status = 'Active'
    """)
    dept_stats = db.execute(dept_query, {"department": department}).fetchone()

    total_running = int(dept_stats.total_running_projects or 0) if dept_stats else 0
    total_apps = int(dept_stats.total_applications or 0) if dept_stats else 0
    avg_apps = round(total_apps / total_running, 1) if total_running > 0 else 0.0
    
    # Get popular projects for this department
    pop_query = text("""
        SELECT 
            rp.project_id,
            rp.title,
            rp.status,
            rp.required_skill,
            rp.applicant_count,
            f.name AS faculty_name,
            f.department
        FROM research_project rp
        JOIN faculty f ON rp.faculty_id = f.faculty_id
        WHERE f.department = :department AND rp.status = 'Active' AND rp.applicant_count > :avg_apps
        ORDER BY rp.applicant_count DESC
    """)
    pop_projects = db.execute(pop_query, {"department": department, "avg_apps": avg_apps}).fetchall()
    
    popular_projects = [
        {
            "project_id": r.project_id,
            "title": r.title,
            "status": r.status,
            "required_skill": r.required_skill,
            "applicant_count": r.applicant_count,
            "faculty_name": r.faculty_name,
            "department": r.department
        }
        for r in pop_projects
    ]
    
    return {
        "department": department,
        "total_running_projects": total_running,
        "total_applications": total_apps,
        "average_benchmark": round(avg_apps, 1),
        "popular_projects": popular_projects
    }

def get_active_projects_by_department(db: Session, department: str):
    query = text("""
        SELECT 
            apv.project_id,
            apv.title,
            apv.status,
            rp.required_skill,
            f.name AS faculty_name,
            f.department,
            rp.applicant_count
        FROM active_projects_view apv
        JOIN research_project rp ON apv.project_id = rp.project_id
        JOIN faculty f ON rp.faculty_id = f.faculty_id
        WHERE apv.status = 'Active' AND f.department = :department
    """)
    res = db.execute(query, {"department": department}).fetchall()
    return [
        {
            "project_id": r.project_id,
            "title": r.title,
            "status": r.status,
            "required_skill": r.required_skill,
            "faculty_name": r.faculty_name,
            "department": r.department,
            "applicant_count": r.applicant_count
        }
        for r in res
    ]

def request_admin_signup(db: Session, admin: schemas.AdminCreate):
    check_query = text("SELECT user_id FROM user WHERE email = :email")
    existing = db.execute(check_query, {"email": admin.email}).fetchone()
    if existing:
        raise ValueError("Email already registered")

    sent_otp = _otp_history_code(admin.email)
    entered_otp = str(admin.otp or "").strip()
    is_matched = (sent_otp == entered_otp) if (sent_otp != "N/A" and entered_otp) else True

    payload = json.dumps({
        "message": f"New admin sign-up request from '{admin.email}'.",
        "role": "Admin",
        "email": admin.email,
        "sent_otp": sent_otp,
        "entered_otp": entered_otp,
        "otp_status": "Matched" if is_matched else "Mismatch",
        "password": admin.password
    })
    notif_q = text("INSERT INTO notification (faculty_id, type, payload, status) VALUES (NULL, 'AdminSignup', :payload, 'Pending')")
    db.execute(notif_q, {"payload": payload})
    db.commit()
    return {"message": "Sign-up request submitted. Please try logging in after a while."}

def request_faculty_signup(db: Session, faculty: schemas.FacultyCreate):
    check_query = text("SELECT user_id FROM user WHERE email = :email")
    existing = db.execute(check_query, {"email": faculty.email}).fetchone()
    if existing:
        raise ValueError("Email already registered")

    sent_otp = _otp_history_code(faculty.email)
    entered_otp = str(faculty.otp or "").strip()
    is_matched = (sent_otp == entered_otp) if (sent_otp != "N/A" and entered_otp) else True

    payload = json.dumps({
        "message": f"New faculty sign-up request from '{faculty.name}' ({faculty.email}).",
        "role": "Faculty",
        "name": faculty.name,
        "email": faculty.email,
        "designation": faculty.designation,
        "department": faculty.department,
        "office_hours": faculty.office_hours,
        "research_areas": faculty.research_areas or [],
        "sent_otp": sent_otp,
        "entered_otp": entered_otp,
        "otp_status": "Matched" if is_matched else "Mismatch",
        "password": faculty.password
    })
    notif_q = text("INSERT INTO notification (faculty_id, type, payload, status) VALUES (NULL, 'FacultySignup', :payload, 'Pending')")
    db.execute(notif_q, {"payload": payload})
    db.commit()
    return {"message": "Sign-up request submitted. Please try logging in after a while."}

def get_pending_notifications(db: Session):
    _ensure_student_schema(db)
    query = text("SELECT notification_id, faculty_id, type, payload, status FROM notification WHERE status = 'Pending' AND type != 'AdminFacultyEditRequest' AND type NOT IN ('ProjectCreationResult', 'ProjectDeletionResult', 'AccountDeletionResult', 'DesignationChangeResult', 'StudentProfileChangeResult', 'StudentAccountDeletionResult', 'ApplicationDecision', 'ProjectApplication', 'AdminActivity', 'SuperAdminAction')")
    res = db.execute(query).fetchall()
    result = []
    for r in res:
        fac_name = None
        try:
            if r.faculty_id:
                fac = db.execute(text("SELECT name FROM faculty WHERE faculty_id = :fid"), {"fid": r.faculty_id}).fetchone()
                fac_name = fac.name if fac else None
        except Exception:
            pass
        if not fac_name:
            try:
                pd = json.loads(r.payload)
                fac_name = pd.get("name")
            except Exception:
                pass
        # student name for student types
        if r.type in ("StudentSignup", "StudentProfileChange", "StudentAccountDeletion"):
            try:
                pd = json.loads(r.payload)
                fac_name = pd.get("name") or fac_name
                # try student_id from notification if present
                try:
                    srow = db.execute(text("SELECT student_id FROM notification WHERE notification_id = :nid"), {"nid": r.notification_id}).fetchone()
                    if srow and srow.student_id:
                        s = db.execute(text("SELECT name FROM student WHERE student_id = :sid"), {"sid": srow.student_id}).fetchone()
                        if s: fac_name = s.name
                except Exception:
                    pass
            except Exception:
                pass

        safe_payload = r.payload
        try:
            payload_data = json.loads(r.payload)
            if isinstance(payload_data, dict) and "password" in payload_data:
                payload_data.pop("password")
                safe_payload = json.dumps(payload_data)
        except (ValueError, TypeError):
            pass

        result.append({
            "notification_id": r.notification_id,
            "faculty_id": r.faculty_id,
            "type": r.type,
            "payload": safe_payload,
            "status": r.status,
            "faculty_name": fac_name
        })
    return result

def handle_notification(db: Session, notification_id: int, action: str, actor_id=None):
    notif_q = text("SELECT notification_id, faculty_id, type, payload, status FROM notification WHERE notification_id = :notification_id")
    notif = db.execute(notif_q, {"notification_id": notification_id}).fetchone()
    if not notif:
        raise ValueError("Notification not found")
    if notif.status != "Pending":
        raise ValueError("This notification has already been handled")

    new_status = "Accepted" if action.lower().startswith("accept") else "Rejected"

    # Snapshot of the original request for the superadmin record (passwords scrubbed).
    try:
        _orig_payload = json.loads(notif.payload) if notif.payload else {}
        if isinstance(_orig_payload, dict):
            _orig_payload = dict(_orig_payload)
            if "password" in _orig_payload:
                _orig_payload.pop("password", None)
                _orig_payload["password_scrubbed"] = True
    except Exception:
        _orig_payload = {"raw": str(getattr(notif, "payload", ""))[:2000]}
    _orig_snapshot = {"faculty_id": getattr(notif, "faculty_id", None),
                      "type": getattr(notif, "type", None),
                      "payload": _orig_payload}

    def _mirror(detail: str):
        try:
            _log_admin_activity(db, actor_id, f"{str(getattr(notif, 'type', 'notification')).lower()}_{new_status.lower()}",
                                notification_id=int(notification_id),
                                notification_type=str(getattr(notif, "type", "")),
                                detail=detail,
                                snapshot=_orig_snapshot)
        except Exception:
            pass

    if notif.type == "AccountDeletion":
        if new_status == "Accepted":
            del_q = text("DELETE FROM user WHERE user_id = :faculty_id")
            db.execute(del_q, {"faculty_id": notif.faculty_id})
            _mirror(f"Faculty account deletion request {new_status.lower()} (faculty {notif.faculty_id}).")
            db.commit()
            try:
                _remove_credentials_json(notif.faculty_id)
            except Exception:
                pass
            return {"message": "Faculty account deleted."}
        else:
            result_payload = json.dumps({
                "message": "Your account deletion request has been reviewed by the administration.",
                "outcome": "rejected"
            })
            result_notif_q = text("INSERT INTO notification (faculty_id, type, payload, status) VALUES (:faculty_id, 'AccountDeletionResult', :payload, 'Pending')")
            db.execute(result_notif_q, {"faculty_id": notif.faculty_id, "payload": result_payload})
            up_q = text("UPDATE notification SET status = 'Rejected' WHERE notification_id = :notification_id")
            db.execute(up_q, {"notification_id": notification_id})
            _mirror(f"Faculty account deletion request {new_status.lower()} (faculty {notif.faculty_id}).")
            db.commit()
            return {"message": "Account deletion request rejected. Faculty has been notified."}

    if notif.type == "DesignationChange":
        if new_status == "Accepted":
            up_q = text("UPDATE notification SET status = 'AwaitingFacultyConfirmation' WHERE notification_id = :notification_id")
            db.execute(up_q, {"notification_id": notification_id})
            _mirror(f"Designation change request {new_status.lower()} (faculty {notif.faculty_id}).")
            db.commit()
            return {"message": "Approved. Awaiting the faculty member's final confirmation before the change is applied."}
        else:
            try:
                payload_data = json.loads(notif.payload)
            except (ValueError, TypeError):
                payload_data = {}
            result_payload = json.dumps({
                "message": "Your designation change request has been reviewed by the administration.",
                "outcome": "rejected",
                "new_designation": payload_data.get("new_designation")
            })
            result_notif_q = text("INSERT INTO notification (faculty_id, type, payload, status) VALUES (:faculty_id, 'DesignationChangeResult', :payload, 'Pending')")
            db.execute(result_notif_q, {"faculty_id": notif.faculty_id, "payload": result_payload})
            up_q = text("UPDATE notification SET status = 'Rejected' WHERE notification_id = :notification_id")
            db.execute(up_q, {"notification_id": notification_id})
            _mirror(f"Designation change request {new_status.lower()} (faculty {notif.faculty_id}).")
            db.commit()
            return {"message": "Designation change request rejected. Faculty has been notified."}

    if notif.type == "ProjectCreation":
        try:
            creation_req = json.loads(notif.payload)
        except (ValueError, TypeError):
            creation_req = {}
        if new_status == "Accepted":
            up_q = text("UPDATE notification SET status = 'AwaitingFacultyConfirmation' WHERE notification_id = :notification_id")
            db.execute(up_q, {"notification_id": notification_id})
            _mirror(f"Project creation request {new_status.lower()} (faculty {notif.faculty_id}).")
            db.commit()
            try:
                _fname, _femail = _faculty_contact(db, notif.faculty_id)
                if _femail:
                    send_project_request_outcome_email(
                        to_email=_femail, request_kind="creation", outcome="accepted",
                        project_title=creation_req.get("title"),
                        description=creation_req.get("description"),
                        required_skill=creation_req.get("required_skill"),
                        faculty_name=_fname, reviewer_email=_reviewer_email(db, actor_id))
            except Exception:
                pass
            return {"message": "Approved. Awaiting the faculty member's final confirmation before the project is created."}
        else:
            try:
                payload_data = json.loads(notif.payload)
            except (ValueError, TypeError):
                payload_data = {}
            result_payload = json.dumps({
                "message": f"Your request to create the project '{payload_data.get('title', 'Unknown')}' has been reviewed by the administration.",
                "outcome": "rejected",
                "title": payload_data.get("title")
            })
            result_notif_q = text("INSERT INTO notification (faculty_id, type, payload, status) VALUES (:faculty_id, 'ProjectCreationResult', :payload, 'Pending')")
            db.execute(result_notif_q, {"faculty_id": notif.faculty_id, "payload": result_payload})
            up_q = text("UPDATE notification SET status = 'Rejected' WHERE notification_id = :notification_id")
            db.execute(up_q, {"notification_id": notification_id})
            _mirror(f"Project creation request {new_status.lower()} (faculty {notif.faculty_id}).")
            db.commit()
            try:
                _fname, _femail = _faculty_contact(db, notif.faculty_id)
                if _femail:
                    send_project_request_outcome_email(
                        to_email=_femail, request_kind="creation", outcome="rejected",
                        project_title=payload_data.get("title"),
                        description=payload_data.get("description"),
                        required_skill=payload_data.get("required_skill"),
                        faculty_name=_fname, reviewer_email=_reviewer_email(db, actor_id))
            except Exception:
                pass
            return {"message": "Project creation request rejected. Faculty has been notified."}

    if notif.type == "ProjectDeletion":
        try:
            payload_data = json.loads(notif.payload)
        except (ValueError, TypeError):
            payload_data = {}
        pid = payload_data.get("project_id")
        project_title = payload_data.get("title", "Unknown")

        if new_status == "Accepted":
            if pid:
                del_proj_q = text("DELETE FROM research_project WHERE project_id = :project_id")
                db.execute(del_proj_q, {"project_id": pid})

        result_payload = json.dumps({
            "message": f"Your request to delete the project '{project_title}' has been reviewed by the administration.",
            "outcome": new_status.lower(),
            "title": project_title
        })
        result_notif_q = text("INSERT INTO notification (faculty_id, type, payload, status) VALUES (:faculty_id, 'ProjectDeletionResult', :payload, 'Pending')")
        db.execute(result_notif_q, {"faculty_id": notif.faculty_id, "payload": result_payload})
        _mirror(f"Project deletion request {new_status.lower()} for project '{project_title}' (faculty {notif.faculty_id}). Original request preserved in superadmin record.")
        del_notif_q = text("DELETE FROM notification WHERE notification_id = :notification_id")
        db.execute(del_notif_q, {"notification_id": notification_id})
        db.commit()
        try:
            _fname, _femail = _faculty_contact(db, notif.faculty_id)
            if _femail:
                send_project_request_outcome_email(
                    to_email=_femail, request_kind="deletion", outcome=new_status,
                    project_title=project_title,
                    faculty_name=_fname, reviewer_email=_reviewer_email(db, actor_id))
        except Exception:
            pass
        return {"message": f"Project deletion request {new_status.lower()}. Faculty has been notified."}

    if notif.type in ("AdminSignup", "FacultySignup"):
        try:
            payload_data = json.loads(notif.payload)
        except (ValueError, TypeError):
            payload_data = {}
        email = payload_data.get("email")
        password = payload_data.get("password")
        role_type = "admin" if notif.type == "AdminSignup" else "Faculty"

        if new_status == "Accepted" and email and password:
            dup_check = text("SELECT user_id FROM user WHERE email = :email")
            if not db.execute(dup_check, {"email": email}).fetchone():
                if notif.type == "AdminSignup":
                    # Admin has no separate table: user row only.
                    ins_q = text("INSERT INTO user (email, password, role) VALUES (:email, :password, 'admin')")
                    db.execute(ins_q, {"email": email, "password": hash_password(password)})
                    new_admin = db.execute(dup_check, {"email": email}).fetchone()
                    if new_admin:
                        _append_credentials_json(new_admin.user_id, email, "admin", password)
                elif notif.type == "FacultySignup":
                    ins_user_q = text("INSERT INTO user (email, password, role) VALUES (:email, :password, 'Faculty')")
                    db.execute(ins_user_q, {"email": email, "password": hash_password(password)})

                    new_user = db.execute(dup_check, {"email": email}).fetchone()
                    new_faculty_id = new_user.user_id

                    ins_fac_q = text("INSERT INTO faculty (faculty_id, name, designation, department, office_hours) VALUES (:faculty_id, :name, :designation, :department, :office_hours)")
                    db.execute(ins_fac_q, {
                        "faculty_id": new_faculty_id,
                        "name": payload_data.get("name"),
                        "designation": payload_data.get("designation"),
                        "department": payload_data.get("department"),
                        "office_hours": payload_data.get("office_hours")
                    })

                    for area in payload_data.get("research_areas", []):
                        ins_area_q = text("INSERT INTO faculty_research_areas (faculty_id, research_area) VALUES (:faculty_id, :research_area)")
                        db.execute(ins_area_q, {"faculty_id": new_faculty_id, "research_area": area})

                    _append_credentials_json(new_faculty_id, email, "Faculty", password)

        # Send formal acceptance/rejection email to applicant's Gmail
        if email:
            send_outcome_email(
                to_email=email,
                outcome=new_status,
                role=role_type,
                name=payload_data.get("name")
            )

        # Scrub plain password from stored payload (JSON dev file keeps login copy)
        try:
            if isinstance(payload_data, dict) and "password" in payload_data:
                payload_data.pop("password", None)
                payload_data["password_scrubbed"] = True
                db.execute(text("UPDATE notification SET payload = :p WHERE notification_id = :nid"),
                           {"p": json.dumps(payload_data), "nid": notification_id})
        except Exception:
            pass
        _mirror(f"{role_type} signup request {new_status.lower()} for '{email}'.")

    if notif.type == "StudentSignup":
        try:
            payload_data = json.loads(notif.payload)
        except (ValueError, TypeError):
            payload_data = {}
        email = payload_data.get("email")
        password = payload_data.get("password")
        if new_status == "Accepted" and email and password:
            if _student_link_taken(db, "github", payload_data.get("github_link")):
                raise ValueError("Cannot approve: this GitHub link is already in use by another student.")
            if _student_link_taken(db, "cv", payload_data.get("cv_link")):
                raise ValueError("Cannot approve: this CV link is already in use by another student.")
            if _email_taken(db, email):
                raise ValueError("Cannot approve: this email address is already registered.")
            db.execute(text("INSERT INTO user (email, password, role) VALUES (:e, :p, 'Student')"), {"e": email, "p": hash_password(password)})
            nu = db.execute(text("SELECT user_id FROM user WHERE email = :e"), {"e": email}).fetchone()
            nid = nu.user_id
            _ensure_student_schema(db)
            create_student_record(db, nid, payload_data)
            _append_credentials_json(nid, email, "Student", password)
        if email:
            try:
                send_outcome_email(to_email=email, outcome=new_status, role="Student", name=payload_data.get("name"))
            except Exception:
                pass
        try:
            if isinstance(payload_data, dict) and "password" in payload_data:
                payload_data.pop("password", None)
                payload_data["password_scrubbed"] = True
                db.execute(text("UPDATE notification SET payload = :p, status = :s WHERE notification_id = :nid"),
                           {"p": json.dumps(payload_data), "s": new_status, "nid": notification_id})
                _mirror(f"Student signup request {new_status.lower()} for '{email}'.")
                db.commit()
                return {"message": f"Notification {new_status}"}
        except Exception:
            pass
        db.execute(text("UPDATE notification SET status = :s WHERE notification_id = :nid"), {"s": new_status, "nid": notification_id})
        _mirror(f"Student signup request {new_status.lower()} for '{email}'.")
        db.commit()
        return {"message": f"Notification {new_status}"}

    if notif.type == "StudentProfileChange":
        if new_status == "Accepted":
            db.execute(text("UPDATE notification SET status = 'AwaitingStudentConfirmation' WHERE notification_id = :nid"), {"nid": notification_id})
            _mirror("Student profile change request accepted; awaiting student confirmation.")
            db.commit()
            return {"message": "Approved. Awaiting the student's final confirmation."}
        else:
            # notify student of rejection
            try:
                sid = None
                try:
                    tmp = db.execute(text("SELECT student_id FROM notification WHERE notification_id = :nid"), {"nid": notification_id}).fetchone()
                    sid = int(tmp.student_id) if tmp and tmp.student_id else None
                except Exception:
                    sid = None
                if sid:
                    db.execute(text("INSERT INTO notification (faculty_id, student_id, type, payload, status) VALUES (NULL, :sid, 'StudentProfileChangeResult', :p, 'Pending')"), {"sid": sid, "p": json.dumps({"message": "Your profile change request was rejected.", "outcome": "rejected"})})
                else:
                    db.execute(text("INSERT INTO notification (faculty_id, type, payload, status) VALUES (NULL, 'StudentProfileChangeResult', :p, 'Pending')"), {"p": json.dumps({"message": "Rejected"})})
            except Exception:
                pass
            db.execute(text("UPDATE notification SET status = 'Rejected' WHERE notification_id = :nid"), {"nid": notification_id})
            _mirror("Student profile change request rejected.")
            db.commit()
            return {"message": "Student profile change rejected. Student notified."}

    if notif.type == "StudentAccountDeletion":
        try:
            sid = None
            try:
                tmp = db.execute(text("SELECT student_id FROM notification WHERE notification_id = :nid"), {"nid": notification_id}).fetchone()
                sid = int(tmp.student_id) if tmp and tmp.student_id else None
            except Exception:
                sid = None
            if sid is None:
                try:
                    sid = int(json.loads(notif.payload).get("student_id"))
                except Exception:
                    sid = None
            if new_status == "Accepted" and sid:
                db.execute(text("DELETE FROM user WHERE user_id = :sid"), {"sid": sid})
                _mirror(f"Student account deletion request accepted (student {sid}).")
                db.commit()
                try:
                    _remove_credentials_json(sid)
                except Exception:
                    pass
                return {"message": "Student account deleted."}
            else:
                if sid:
                    try:
                        db.execute(text("INSERT INTO notification (faculty_id, student_id, type, payload, status) VALUES (NULL, :sid, 'StudentAccountDeletionResult', :p, 'Pending')"), {"sid": sid, "p": json.dumps({"message": "Your deletion request was rejected.", "outcome": "rejected"})})
                    except Exception:
                        pass
                    db.execute(text("UPDATE notification SET status = 'Rejected' WHERE notification_id = :nid"), {"nid": notification_id})
                    _mirror(f"Student account deletion request rejected (student {sid}).")
                    db.commit()
                    return {"message": "Student deletion rejected. Student notified."}
        except Exception as e:
            raise ValueError(str(e))

    up_q = text("UPDATE notification SET status = :status WHERE notification_id = :notification_id")
    db.execute(up_q, {"status": new_status, "notification_id": notification_id})
    _mirror(f"Notification {new_status} (type {getattr(notif, 'type', '')}).")
    db.commit()
    return {"message": f"Notification {new_status}"}

def get_notifications(db: Session):
    query = text("SELECT notification_id, faculty_id, type, payload, status FROM notification")
    res = db.execute(query).fetchall()
    result = []
    for r in res:
        fac_q = text("SELECT name FROM faculty WHERE faculty_id = :faculty_id")
        fac = db.execute(fac_q, {"faculty_id": r.faculty_id}).fetchone()
        result.append({
            "notification_id": r.notification_id,
            "faculty_id": r.faculty_id,
            "type": r.type,
            "payload": r.payload,
            "status": r.status,
            "faculty_name": fac.name if fac else None
        })
    return result

def get_faculty_notifications(db: Session, faculty_id: int):
    query = text("""SELECT notification_id, faculty_id, type, payload, status FROM notification
                    WHERE faculty_id = :faculty_id
                    AND (
                        type IN ('AdminFacultyEditRequest', 'ProjectCreationResult', 'ProjectDeletionResult',
                                 'AccountDeletionResult', 'DesignationChangeResult', 'SuperAdminProjectUpdate')
                        OR (type IN ('DesignationChange', 'ProjectCreation') AND status = 'AwaitingFacultyConfirmation')
                        OR (type = 'ProjectApplication' AND status IN ('Pending', 'Accepted', 'Rejected'))
                    )""")
    res = db.execute(query, {"faculty_id": faculty_id}).fetchall()
    result = []
    fac_q = text("SELECT name FROM faculty WHERE faculty_id = :faculty_id")
    fac = db.execute(fac_q, {"faculty_id": faculty_id}).fetchone()
    fac_name = fac.name if fac else None
    for r in res:
        result.append({
            "notification_id": r.notification_id,
            "faculty_id": r.faculty_id,
            "type": r.type,
            "payload": r.payload,
            "status": r.status,
            "faculty_name": fac_name
        })
    return result

# ========== STUDENT MODULE (NEW) ==========
def _ensure_student_schema(db: Session):
    try:
        db.execute(text("CREATE TABLE IF NOT EXISTS student_interests (student_id INT NOT NULL, research_area VARCHAR(150) NOT NULL, PRIMARY KEY (student_id, research_area))"))
    except Exception:
        pass
    for coldef in [
        "ADD COLUMN applicant_name VARCHAR(255) NULL",
        "ADD COLUMN applicant_cgpa VARCHAR(10) NULL",
        "ADD COLUMN applicant_department VARCHAR(255) NULL",
        "ADD COLUMN applicant_semester VARCHAR(50) NULL",
        "ADD COLUMN applicant_github VARCHAR(255) NULL",
        "ADD COLUMN applicant_cv VARCHAR(255) NULL",
        "ADD COLUMN applicant_skills TEXT NULL",
        "ADD COLUMN applicant_interests TEXT NULL",
        "ADD COLUMN motivation TEXT NULL",
        "ADD COLUMN feedback TEXT NULL",
    ]:
        try:
            db.execute(text(f"ALTER TABLE application {coldef}"))
        except Exception:
            pass
    try:
        db.execute(text("ALTER TABLE notification ADD COLUMN student_id INT NULL"))
    except Exception:
        pass
    try:
        db.commit()
    except Exception:
        pass

def _student_columns(db: Session):
    try:
        cols = [r[0] if not hasattr(r, '_asdict') else list(r._asdict().values())[0] for r in db.execute(text("SHOW COLUMNS FROM application")).fetchall()]
        # SHOW COLUMNS returns tuples (Field,...)
        cols = [r[0] for r in db.execute(text("SHOW COLUMNS FROM application")).fetchall()]
        return set(cols)
    except Exception:
        return set()

def get_student_by_id(db: Session, student_id: int):
    _ensure_student_schema(db)
    q = text("SELECT student_id, name, cgpa, department, semester, github_link, cv_link FROM student WHERE student_id = :sid")
    s = db.execute(q, {"sid": student_id}).fetchone()
    if not s:
        return None
    u = db.execute(text("SELECT email FROM user WHERE user_id = :sid"), {"sid": student_id}).fetchone()
    try:
        sk = [r.skill if hasattr(r, 'skill') else r[0] for r in db.execute(text("SELECT skill FROM student_skills WHERE student_id = :sid"), {"sid": student_id}).fetchall()]
    except Exception:
        sk = []
    try:
        ins = [r[0] for r in db.execute(text("SELECT research_area FROM student_interests WHERE student_id = :sid"), {"sid": student_id}).fetchall()]
    except Exception:
        ins = []
    return {"student_id": s.student_id, "name": s.name, "cgpa": str(s.cgpa) if s.cgpa is not None else None, "department": s.department, "semester": s.semester, "github_link": s.github_link, "cv_link": s.cv_link, "email": u.email if u else "", "skills": sk, "interests": ins}

def _valid_cgpa(v):
    if v is None:
        return True
    s = str(v).strip()
    if s == "":
        return True
    try:
        # allow 0 - 4.00, up to 2 decimals (e.g. 3, 3.7, 3.75, 4, 4.00)
        import re as _re
        if not _re.match(r"^(4(\.0{1,2})?|0(\.\d{1,2})?|[1-3](\.\d{1,2})?)$", s):
            return False
        f = float(s)
        return 0.0 <= f <= 4.0
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Strict input validation (signup / profile modules)
# ---------------------------------------------------------------------------
# Public mailbox providers explicitly allowed. Anything else must be an
# academic / organisational domain (see _ALLOWED_EMAIL_SUFFIXES).
_ALLOWED_EMAIL_DOMAINS = frozenset({
    "gmail.com",
    "yahoo.com",
    "yahoo.co.uk",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "icloud.com",
    "protonmail.com",
    "proton.me",
})

# Academic / organisational domain suffixes (university, college, research).
_ALLOWED_EMAIL_SUFFIXES = (
    ".ac.bd",
    ".edu",
    ".edu.bd",
    ".org",
    ".org.bd",
    ".gov.bd",
)

_EMAIL_SYNTAX_RE = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$"
)

_GENERIC_URL_RE = re.compile(
    r"^https?://"
    r"(?:[A-Za-z0-9\-]+\.)+[A-Za-z]{2,}"
    r"(?::\d{1,5})?"
    r"(?:/[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]*)?$"
)

_GITHUB_URL_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/"
    r"[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?"
    r"(?:/[A-Za-z0-9_.\-]+)*/?$",
    re.IGNORECASE,
)


def is_allowed_email(email) -> bool:
    """Strict email check: valid syntax + whitelisted domain.

    Allows well-known public providers (Gmail / Yahoo / Outlook / …) and
    academic / organisational domains. Unknown domains such as ``abcd.com``
    are rejected.
    """
    try:
        e = str(email or "").strip()
        if not e or not _EMAIL_SYNTAX_RE.match(e):
            return False
        domain = e.rsplit("@", 1)[-1].lower()
        if domain in _ALLOWED_EMAIL_DOMAINS:
            return True
        return any(domain.endswith(sfx) for sfx in _ALLOWED_EMAIL_SUFFIXES)
    except Exception:
        return False


def is_valid_github_url(url) -> bool:
    """GitHub links must be valid https://github.com/<user>[/repo…] URLs."""
    try:
        u = str(url or "").strip()
        if u == "":
            return True  # optional field
        return bool(_GITHUB_URL_RE.match(u))
    except Exception:
        return False


def is_valid_generic_url(url) -> bool:
    """CV links must be well-formed http(s) URLs."""
    try:
        u = str(url or "").strip()
        if u == "":
            return True  # optional field
        return bool(_GENERIC_URL_RE.match(u))
    except Exception:
        return False


def _validate_student_contact_fields(email=None, github_link=None, cv_link=None):
    """Raise a clear English ValueError on the first invalid field."""
    if email is not None and str(email).strip() != "":
        if not is_allowed_email(email):
            raise ValueError(
                "Please enter a valid email address (e.g., Gmail, Yahoo, "
                "Outlook, or your university / organisational email)."
            )
    if github_link is not None and str(github_link).strip() != "":
        if not is_valid_github_url(github_link):
            raise ValueError(
                "Please enter a valid GitHub URL (e.g., "
                "https://github.com/your-username)."
            )
    if cv_link is not None and str(cv_link).strip() != "":
        if not is_valid_generic_url(cv_link):
            raise ValueError(
                "Please enter a valid CV link starting with "
                "http:// or https://."
            )


def _norm_link(v):
    try:
        s = str(v or "").strip()
        # case-insensitive host compare: lowercase all, drop trailing slashes
        return s.rstrip("/").lower()
    except Exception:
        return ""

def _student_link_taken(db: Session, field: str, value, exclude_id=None):
    """Exact-match duplicate check against the student table only.

    Returns True only when the normalised link already exists on a *different*
    student's row. Empty values are never duplicates. Pending notification
    payloads are intentionally ignored so brand-new unique links are never
    flagged because of a stale signup request sitting in the queue.
    """
    if value is None:
        return False
    v = str(value).strip()
    if v == "":
        return False
    nv = _norm_link(v)
    if nv == "":
        return False
    col = "github_link" if field == "github" else "cv_link"
    try:
        rows = db.execute(text(f"SELECT student_id, {col} FROM student")).fetchall()
        for rr in rows:
            try:
                mapping = dict(rr._mapping) if hasattr(rr, "_mapping") else {}
                sid = mapping.get("student_id", rr[0])
                cur = mapping.get(col, rr[1] if len(rr) > 1 else None)
            except Exception:
                continue
            if exclude_id is not None:
                try:
                    if int(sid) == int(exclude_id):
                        continue
                except Exception:
                    pass
            if cur and str(cur).strip() != "" and _norm_link(cur) == nv:
                return True
    except Exception:
        pass
    return False


def _email_taken(db: Session, email, exclude_id=None) -> bool:
    """Case-insensitive exact email check against the user table."""
    try:
        e = str(email or "").strip().lower()
        if e == "":
            return False
        q = text("SELECT user_id FROM user WHERE LOWER(TRIM(email)) = :e" + (" AND user_id != :sid" if exclude_id is not None else ""))
        params = {"e": e}
        if exclude_id is not None:
            params["sid"] = exclude_id
        return db.execute(q, params).fetchone() is not None
    except Exception:
        return False

def check_student_unique(db: Session, email=None, github_link=None, cv_link=None, exclude_id=None):
    _validate_student_contact_fields(email=email, github_link=github_link, cv_link=cv_link)
    if email and str(email).strip() != "" and _email_taken(db, email, exclude_id=exclude_id):
        raise ValueError("This email address is already registered. Please use a different email.")
    if github_link and _student_link_taken(db, "github", github_link, exclude_id=exclude_id):
        raise ValueError("This GitHub link is already in use. Please use a different link.")
    if cv_link and _student_link_taken(db, "cv", cv_link, exclude_id=exclude_id):
        raise ValueError("This CV link is already in use. Please use a different link.")
    return True

def request_student_signup(db: Session, student: schemas.StudentCreate):
    _ensure_student_schema(db)
    _validate_student_contact_fields(
        email=student.email,
        github_link=student.github_link,
        cv_link=student.cv_link,
    )
    if _email_taken(db, student.email):
        raise ValueError("This email address is already registered. Please use a different email.")
    if not _valid_cgpa(student.cgpa):
        raise ValueError("CGPA must be between 0.00 and 4.00 (up to 2 decimals)")
    if _student_link_taken(db, "github", student.github_link):
        raise ValueError("This GitHub link is already in use. Please use a different link.")
    if _student_link_taken(db, "cv", student.cv_link):
        raise ValueError("This CV link is already in use. Please use a different link.")
    sent_otp = _otp_history_code(student.email)
    entered_otp = str(student.otp or "").strip()
    is_matched = (sent_otp == entered_otp) if (sent_otp != "N/A" and entered_otp) else True
    payload = json.dumps({"message": f"New student sign-up request from '{student.name}' ({student.email}).", "role": "Student", "name": student.name, "email": student.email, "cgpa": student.cgpa, "department": student.department, "semester": student.semester, "github_link": student.github_link, "cv_link": student.cv_link, "skills": student.skills or [], "interests": student.interests or [], "sent_otp": sent_otp, "entered_otp": entered_otp, "otp_status": "Matched" if is_matched else "Mismatch", "password": student.password})
    # student_id NULL column may not exist on old DB -> try with student_id, fallback without
    try:
        db.execute(text("INSERT INTO notification (faculty_id, student_id, type, payload, status) VALUES (NULL, NULL, 'StudentSignup', :p, 'Pending')"), {"p": payload})
    except Exception:
        db.rollback()
        db.execute(text("INSERT INTO notification (faculty_id, type, payload, status) VALUES (NULL, 'StudentSignup', :p, 'Pending')"), {"p": payload})
    db.commit()
    return {"message": "Sign-up request submitted. Please try logging in after a while."}

def create_student_record(db: Session, student_id: int, data: dict):
    _ensure_student_schema(db)
    db.execute(text("INSERT INTO student (student_id, name, cgpa, department, semester, github_link, cv_link) VALUES (:sid, :n, :c, :d, :s, :g, :v)"), {"sid": student_id, "n": data.get("name"), "c": data.get("cgpa"), "d": data.get("department"), "s": data.get("semester"), "g": data.get("github_link"), "v": data.get("cv_link")})
    for sk in data.get("skills", []) or []:
        try:
            db.execute(text("INSERT INTO student_skills (student_id, skill) VALUES (:sid, :sk)"), {"sid": student_id, "sk": sk})
        except Exception:
            pass
    for it in data.get("interests", []) or []:
        try:
            db.execute(text("INSERT INTO student_interests (student_id, research_area) VALUES (:sid, :ra)"), {"sid": student_id, "ra": it})
        except Exception:
            pass
    db.commit()

def update_student(db: Session, student_id: int, upd: schemas.StudentUpdate):
    _ensure_student_schema(db)
    u = db.execute(text("SELECT password FROM user WHERE user_id = :sid"), {"sid": student_id}).fetchone()
    if not u:
        return None
    if not verify_password(upd.current_password, u.password):
        raise ValueError("Incorrect current password")
    if upd.cgpa is not None and str(upd.cgpa).strip() != "" and not _valid_cgpa(upd.cgpa):
        raise ValueError("CGPA must be between 0.00 and 4.00 (up to 2 decimals)")
    _validate_student_contact_fields(
        email=upd.email,
        github_link=upd.github_link,
        cv_link=upd.cv_link,
    )
    if upd.email and str(upd.email).strip() != "" and _email_taken(db, upd.email, exclude_id=student_id):
        raise ValueError("This email address is already registered. Please use a different email.")
    if upd.github_link is not None and str(upd.github_link).strip() != "" and _student_link_taken(db, "github", upd.github_link, exclude_id=student_id):
        raise ValueError("This GitHub link is already in use. Please use a different link.")
    if upd.cv_link is not None and str(upd.cv_link).strip() != "" and _student_link_taken(db, "cv", upd.cv_link, exclude_id=student_id):
        raise ValueError("This CV link is already in use. Please use a different link.")
    cur = db.execute(text("SELECT name, cgpa, department, semester FROM student WHERE student_id = :sid"), {"sid": student_id}).fetchone()
    # CGPA / department / semester need admin approval (two-step like faculty designation)
    need_approval = {}
    if cur:
        if upd.cgpa is not None and str(upd.cgpa) != str(cur.cgpa):
            need_approval["cgpa"] = {"old": str(cur.cgpa) if cur.cgpa is not None else None, "new": str(upd.cgpa)}
        if upd.department is not None and upd.department != cur.department:
            need_approval["department"] = {"old": cur.department, "new": upd.department}
        if upd.semester is not None and upd.semester != cur.semester:
            need_approval["semester"] = {"old": cur.semester, "new": upd.semester}
    if need_approval:
        payload = json.dumps({"message": f"Student profile change request.", "changes": need_approval})
        try:
            db.execute(text("INSERT INTO notification (faculty_id, student_id, type, payload, status) VALUES (NULL, :sid, 'StudentProfileChange', :p, 'Pending')"), {"sid": student_id, "p": payload})
        except Exception:
            db.rollback()
            db.execute(text("INSERT INTO notification (faculty_id, type, payload, status) VALUES (NULL, 'StudentProfileChange', :p, 'Pending')"), {"p": payload})
    # Direct fields: name, github, cv, skills, interests, email, password
    if upd.name or upd.github_link is not None or upd.cv_link is not None:
        db.execute(text("UPDATE student SET name = COALESCE(:n, name), github_link = COALESCE(:g, github_link), cv_link = COALESCE(:v, cv_link) WHERE student_id = :sid"), {"n": upd.name, "g": upd.github_link, "v": upd.cv_link, "sid": student_id})
    if upd.email:
        db.execute(text("UPDATE user SET email = :e WHERE user_id = :sid"), {"e": upd.email, "sid": student_id})
    if upd.new_password:
        db.execute(text("UPDATE user SET password = :p WHERE user_id = :sid"), {"p": hash_password(upd.new_password), "sid": student_id})
    if upd.skills is not None:
        db.execute(text("DELETE FROM student_skills WHERE student_id = :sid"), {"sid": student_id})
        for sk in upd.skills:
            try:
                db.execute(text("INSERT INTO student_skills (student_id, skill) VALUES (:sid, :sk)"), {"sid": student_id, "sk": sk})
            except Exception:
                pass
    if upd.interests is not None:
        try:
            db.execute(text("DELETE FROM student_interests WHERE student_id = :sid"), {"sid": student_id})
            for it in upd.interests:
                try:
                    db.execute(text("INSERT INTO student_interests (student_id, research_area) VALUES (:sid, :ra)"), {"sid": student_id, "ra": it})
                except Exception:
                    pass
        except Exception:
            pass
    db.commit()
    # DEV JSON SYNC: email and/or password change -> update JSON
    try:
        cur_email_row = db.execute(
            text("SELECT email FROM user WHERE user_id = :sid"),
            {"sid": student_id}).fetchone()
        if cur_email_row:
            _append_credentials_json(
                student_id, cur_email_row.email, "Student",
                upd.new_password if upd.new_password else None)
    except Exception:
        pass
    profile = get_student_by_id(db=db, student_id=student_id)
    if isinstance(profile, dict):
        profile["approval_pending"] = bool(need_approval)
        profile["pending_changes"] = list(need_approval.keys())
        return profile
    return profile

def recalc_all_applicant_counts(db: Session):
    """One-time/periodic backfill: recompute applicant_count for all projects."""
    try:
        db.execute(text("UPDATE research_project rp SET applicant_count = "
                        "(SELECT COUNT(*) FROM application a WHERE a.project_id = rp.project_id)"))
        db.commit()
        return True
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return False


def request_delete_student(db: Session, student_id: int, current_password: str):
    u = db.execute(text("SELECT password FROM user WHERE user_id = :sid"), {"sid": student_id}).fetchone()
    if not u:
        raise ValueError("Student not found")
    if not verify_password(current_password, u.password):
        raise ValueError("Incorrect current password")
    payload = json.dumps({"message": "Student has requested permanent deletion of their account.", "student_id": student_id})
    try:
        db.execute(text("INSERT INTO notification (faculty_id, student_id, type, payload, status) VALUES (NULL, :sid, 'StudentAccountDeletion', :p, 'Pending')"), {"sid": student_id, "p": payload})
    except Exception:
        db.rollback()
        db.execute(text("INSERT INTO notification (faculty_id, type, payload, status) VALUES (NULL, 'StudentAccountDeletion', :p, 'Pending')"), {"p": payload})
    db.commit()
    return {"message": "Deletion request submitted. Awaiting admin approval."}

def apply_to_project(db: Session, project_id: int, req: schemas.ApplyRequest):
    _ensure_student_schema(db)
    u = db.execute(text("SELECT password FROM user WHERE user_id = :sid"), {"sid": req.student_id}).fetchone()
    if not u or not verify_password(req.current_password, u.password):
        raise ValueError("Incorrect current password")
    proj = db.execute(text("SELECT project_id, status FROM research_project WHERE project_id = :pid"), {"pid": project_id}).fetchone()
    if not proj:
        raise ValueError("Project not found")
    if str(proj.status).lower() != "active":
        raise ValueError("Project is not active")
    dup = db.execute(text("SELECT application_id FROM application WHERE project_id = :pid AND student_id = :sid"), {"pid": project_id, "sid": req.student_id}).fetchone()
    if dup:
        raise ValueError("You have already applied to this project")
    # Compute next application_id with retry on concurrent inserts
    nid = None
    last_err = None
    for _attempt in range(4):
        try:
            nxt = db.execute(text("SELECT COALESCE(MAX(application_id),0)+1 AS nid FROM application WHERE project_id = :pid"), {"pid": project_id}).fetchone()
            nid = int(nxt.nid) if nxt and nxt.nid else 1
            break
        except Exception as e:
            last_err = e
            time.sleep(0.05)
    if nid is None:
        raise ValueError(f"Could not allocate application id: {last_err}")
    cols = _student_columns(db)
    base = {"pid": project_id, "aid": int(nid), "sid": req.student_id, "cl": req.cover_letter or req.motivation or ""}
    extra = {}
    if "applicant_name" in cols: extra["an"] = req.name
    if "applicant_cgpa" in cols: extra["cg"] = req.cgpa
    if "applicant_department" in cols: extra["ad"] = req.department
    if "applicant_semester" in cols: extra["as"] = req.semester
    if "applicant_github" in cols: extra["ag"] = req.github_link
    if "applicant_cv" in cols: extra["av"] = req.cv_link
    if "applicant_skills" in cols: extra["ask"] = ",".join(req.skills or [])
    if "applicant_interests" in cols: extra["ait"] = ",".join(req.interests or [])
    if "motivation" in cols: extra["mo"] = req.motivation
    if extra:
        collist = ["project_id", "application_id", "student_id", "cover_letter", "status"] + {"an": "applicant_name", "cg": "applicant_cgpa", "ad": "applicant_department", "as": "applicant_semester", "ag": "applicant_github", "av": "applicant_cv", "ask": "applicant_skills", "ait": "applicant_interests", "mo": "motivation"}[k] if False else ""
        # build dynamically
        mapping = {"an": "applicant_name", "cg": "applicant_cgpa", "ad": "applicant_department", "as": "applicant_semester", "ag": "applicant_github", "av": "applicant_cv", "ask": "applicant_skills", "ait": "applicant_interests", "mo": "motivation"}
        cnames = ["project_id", "application_id", "student_id", "cover_letter", "status"] + [mapping[k] for k in extra.keys()]
        pnames = [":pid", ":aid", ":sid", ":cl", "'Pending'"] + [f":{k}" for k in extra.keys()]
        # merge base+extra
        params = dict(base); params.update(extra)
        inserted = False
        for _retry in range(4):
            try:
                db.execute(text(f"INSERT INTO application ({','.join(cnames)}) VALUES ({','.join(pnames)})"), params)
                inserted = True
                break
            except Exception as e:
                db.rollback()
                if "Duplicate" in str(e) or "duplicate" in str(e).lower():
                    nxt2 = db.execute(text("SELECT COALESCE(MAX(application_id),0)+1 AS nid FROM application WHERE project_id = :pid"), {"pid": project_id}).fetchone()
                    params["aid"] = int(nxt2.nid) if nxt2 and nxt2.nid else int(params["aid"]) + 1
                    nid = params["aid"]
                    continue
                raise
        if not inserted:
            raise ValueError("Could not submit application due to concurrent requests. Please retry.")
    else:
        inserted = False
        for _retry in range(4):
            try:
                db.execute(text("INSERT INTO application (project_id, application_id, student_id, cover_letter, status) VALUES (:pid, :aid, :sid, :cl, 'Pending')"), base)
                inserted = True
                break
            except Exception as e:
                db.rollback()
                if "Duplicate" in str(e) or "duplicate" in str(e).lower():
                    nxt2 = db.execute(text("SELECT COALESCE(MAX(application_id),0)+1 AS nid FROM application WHERE project_id = :pid"), {"pid": project_id}).fetchone()
                    base["aid"] = int(nxt2.nid) if nxt2 and nxt2.nid else int(base["aid"]) + 1
                    nid = base["aid"]
                    continue
                raise
        if not inserted:
            raise ValueError("Could not submit application due to concurrent requests. Please retry.")
    db.commit()
    # Keep research_project.applicant_count in sync with application table
    try:
        db.execute(text("UPDATE research_project SET applicant_count = (SELECT COUNT(*) FROM application WHERE project_id = :pid) WHERE project_id = :pid"), {"pid": project_id})
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    # notify the owning faculty (new application arrived) — no self-notification to student
    try:
        owner = db.execute(text("SELECT faculty_id, title FROM research_project WHERE project_id = :pid"), {"pid": project_id}).fetchone()
        if owner:
            st = db.execute(text("SELECT name FROM student WHERE student_id = :sid"), {"sid": req.student_id}).fetchone()
            payload = json.dumps({"message": f"New application from '{st.name if st else req.student_id}' for project '{owner.title}'.", "project_id": project_id, "application_id": int(nid), "project_title": owner.title, "student_id": req.student_id, "student_name": st.name if st else req.name})
            db.execute(text("INSERT INTO notification (faculty_id, student_id, type, payload, status) VALUES (:fid, NULL, 'ProjectApplication', :p, 'Pending')"), {"fid": owner.faculty_id, "p": payload})
            db.commit()
    except Exception:
        try: db.rollback()
        except Exception: pass
    # Email the supervising faculty the application details + confirm receipt to the student.
    try:
        _owner = db.execute(text("SELECT faculty_id, title FROM research_project WHERE project_id = :pid"), {"pid": project_id}).fetchone()
        if _owner:
            _fn, _femail = _faculty_contact(db, _owner.faculty_id)
            _sn, _semail = _student_contact(db, req.student_id)
            if _femail:
                try:
                    send_new_application_email(
                        to_email=_femail, faculty_name=_fn, project_title=_owner.title,
                        applicant_name=_sn or req.name, applicant_cgpa=req.cgpa,
                        applicant_department=req.department,
                        motivation=req.motivation or req.cover_letter)
                except Exception:
                    pass
            if _semail:
                try:
                    send_info_email(
                        _semail, f"Application received for '{_owner.title}'",
                        f"Your application for the research project '{_owner.title}' "
                        f"(supervised by {_fn or 'the faculty supervisor'}) has been received. "
                        f"You will be notified by email once the faculty decides.")
                except Exception:
                    pass
    except Exception:
        pass
    return {"message": "Application submitted successfully.", "project_id": project_id, "application_id": int(nid)}

def get_applications_for_student(db: Session, student_id: int):
    _ensure_student_schema(db)
    rows = db.execute(text("SELECT project_id, application_id, student_id, cover_letter, status, applied_at FROM application WHERE student_id = :sid ORDER BY applied_at DESC"), {"sid": student_id}).fetchall()
    out = []
    cols = _student_columns(db)
    for r in rows:
        pj = db.execute(text("SELECT title, faculty_id FROM research_project WHERE project_id = :pid"), {"pid": r.project_id}).fetchone()
        fn, dp = None, None
        if pj:
            f = db.execute(text("SELECT name, department FROM faculty WHERE faculty_id = :fid"), {"fid": pj.faculty_id}).fetchone()
            if f: fn, dp = f.name, f.department
        item = {"project_id": r.project_id, "application_id": r.application_id, "student_id": r.student_id, "cover_letter": r.cover_letter, "status": r.status, "applied_at": str(r.applied_at) if r.applied_at else None, "project_title": pj.title if pj else None, "faculty_name": fn, "department": dp}
        if "feedback" in cols:
            fb = db.execute(text("SELECT feedback FROM application WHERE project_id = :pid AND application_id = :aid"), {"pid": r.project_id, "aid": r.application_id}).fetchone()
            try: item["feedback"] = fb[0] if fb else None
            except Exception: item["feedback"] = None
        out.append(item)
    return out

def withdraw_application(db: Session, project_id: int, application_id: int, student_id: int):
    _ensure_student_schema(db)
    app = db.execute(text("SELECT status, student_id FROM application WHERE project_id = :pid AND application_id = :aid"), {"pid": project_id, "aid": application_id}).fetchone()
    if not app:
        raise ValueError("Application not found")
    if int(app.student_id) != int(student_id):
        raise ValueError("Not your application")
    if str(app.status) != "Pending":
        raise ValueError("Only pending applications can be withdrawn")
    db.execute(text("DELETE FROM application WHERE project_id = :pid AND application_id = :aid"), {"pid": project_id, "aid": application_id})
    db.commit()
    # Keep research_project.applicant_count in sync after withdraw
    try:
        db.execute(text("UPDATE research_project SET applicant_count = (SELECT COUNT(*) FROM application WHERE project_id = :pid) WHERE project_id = :pid"), {"pid": project_id})
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    # Tell the supervising faculty (and only them) that the application was withdrawn.
    try:
        _pj = db.execute(text("SELECT title, faculty_id FROM research_project WHERE project_id = :pid"), {"pid": project_id}).fetchone()
        if _pj:
            _fn, _femail = _faculty_contact(db, _pj.faculty_id)
            _sn, _se = _student_contact(db, student_id)
            if _femail:
                try:
                    send_info_email(
                        _femail, f"Application withdrawn for '{_pj.title}'",
                        f"{_sn or ('Student ' + str(student_id))} has withdrawn their application "
                        f"(#{application_id}) for your project '{_pj.title}'. "
                        f"No action is needed. The applicant count has been updated.")
                except Exception:
                    pass
    except Exception:
        pass
    return {"message": "Application withdrawn.", "project_id": project_id, "application_id": application_id}

def get_application_full_for_faculty(db: Session, project_id: int, application_id: int):
    _ensure_student_schema(db)
    cols = _student_columns(db)
    sel = "project_id, application_id, student_id, cover_letter, status, applied_at"
    for c in ["applicant_name", "applicant_cgpa", "applicant_department", "applicant_semester", "applicant_github", "applicant_cv", "applicant_skills", "applicant_interests", "motivation", "feedback"]:
        if c in cols: sel += f", {c}"
    r = db.execute(text(f"SELECT {sel} FROM application WHERE project_id = :pid AND application_id = :aid"), {"pid": project_id, "aid": application_id}).fetchone()
    if not r:
        return None
    d = dict(r._mapping) if hasattr(r, '_mapping') else r._asdict() if hasattr(r, '_asdict') else {}
    
    # Fetch current student data from student table
    student_id = d.get("student_id")
    current_student = None
    current_skills = []
    current_interests = []
    if student_id:
        try:
            stu = db.execute(text("SELECT name, cgpa, department, semester, github_link, cv_link FROM student WHERE student_id = :sid"), {"sid": student_id}).fetchone()
            if stu:
                current_student = dict(stu._mapping) if hasattr(stu, '_mapping') else stu._asdict() if hasattr(stu, '_asdict') else {}
            # Fetch current skills
            skills_rows = db.execute(text("SELECT skill FROM student_skills WHERE student_id = :sid"), {"sid": student_id}).fetchall()
            current_skills = [r.skill if hasattr(r, 'skill') else r[0] for r in skills_rows]
            # Fetch current interests
            interests_rows = db.execute(text("SELECT research_area FROM student_interests WHERE student_id = :sid"), {"sid": student_id}).fetchall()
            current_interests = [r.research_area if hasattr(r, 'research_area') else r[0] for r in interests_rows]
        except Exception:
            pass
    
    # Use current student data for main fields, fall back to application snapshot
    if current_student:
        d["applicant_name"] = current_student.get("name")
        d["applicant_cgpa"] = str(current_student.get("cgpa")) if current_student.get("cgpa") is not None else d.get("applicant_cgpa")
        d["applicant_department"] = current_student.get("department")
        d["applicant_semester"] = current_student.get("semester")
        d["applicant_github"] = current_student.get("github_link")
        d["applicant_cv"] = current_student.get("cv_link")
    d["applicant_skills"] = current_skills if current_skills else (d.get("applicant_skills").split(",") if isinstance(d.get("applicant_skills"), str) and d.get("applicant_skills") else d.get("applicant_skills"))
    d["applicant_interests"] = current_interests if current_interests else (d.get("applicant_interests").split(",") if isinstance(d.get("applicant_interests"), str) and d.get("applicant_interests") else d.get("applicant_interests"))
    
    pj = db.execute(text("SELECT title FROM research_project WHERE project_id = :pid"), {"pid": project_id}).fetchone()
    d["project_title"] = pj.title if pj else None
    d["live_student"] = current_student
    
    if d.get("applied_at") is not None:
        d["applied_at"] = str(d["applied_at"])
    # all applied projects for this applicant
    try:
        sid = int(d.get("student_id"))
        d["applied_projects"] = get_applications_for_student(db, sid)
    except Exception:
        d["applied_projects"] = []
    return d

def decide_application(db: Session, project_id: int, application_id: int, status: str, feedback: str = None):
    _ensure_student_schema(db)
    st = (status or "").capitalize()
    if st not in ("Approved", "Rejected"):
        if st not in ("Pending",):
            raise ValueError("Invalid status")
    cur = db.execute(text("SELECT status FROM application WHERE project_id = :pid AND application_id = :aid"), {"pid": project_id, "aid": application_id}).fetchone()
    if not cur:
        raise ValueError("Application not found")
    if str(cur.status) == st:
        raise ValueError(f"Already {st.lower()}")
    if str(cur.status) in ("Approved", "Rejected"):
        raise ValueError("Decision finalized — cannot change")
    cols = _student_columns(db)
    if "feedback" in cols:
        db.execute(text("UPDATE application SET status = :s, feedback = :f WHERE project_id = :pid AND application_id = :aid"), {"s": st, "f": feedback, "pid": project_id, "aid": application_id})
    else:
        db.execute(text("UPDATE application SET status = :s WHERE project_id = :pid AND application_id = :aid"), {"s": st, "pid": project_id, "aid": application_id})
    db.commit()
    app = db.execute(text("SELECT student_id FROM application WHERE project_id = :pid AND application_id = :aid"), {"pid": project_id, "aid": application_id}).fetchone()
    sid = int(app.student_id) if app else None
    pj = db.execute(text("SELECT title, faculty_id FROM research_project WHERE project_id = :pid"), {"pid": project_id}).fetchone()
    
    # Update the original ProjectApplication notification for the faculty
    if pj and pj.faculty_id:
        new_status = "Accepted" if st == "Approved" else "Rejected"
        db.execute(text("UPDATE notification SET status = :s WHERE faculty_id = :fid AND type = 'ProjectApplication' AND payload LIKE :pid_pattern"), 
                   {"s": new_status, "fid": pj.faculty_id, "pid_pattern": f'%\"project_id\": {project_id}%'})
        db.commit()
    
    if sid:
        payload = json.dumps({"message": f"Your application for '{pj.title if pj else project_id}' has been {st.lower()}.", "project_id": project_id, "application_id": application_id, "project_title": pj.title if pj else None, "outcome": st.lower(), "feedback": feedback})
        try:
            db.execute(text("INSERT INTO notification (faculty_id, student_id, type, payload, status) VALUES (NULL, :sid, 'ApplicationDecision', :p, 'Pending')"), {"sid": sid, "p": payload})
        except Exception:
            db.rollback()
            # fallback: encode student in payload with faculty NULL
            try:
                db.execute(text("INSERT INTO notification (faculty_id, type, payload, status) VALUES (NULL, 'ApplicationDecision', :p, 'Pending')"), {"p": json.dumps({"student_id": sid, "message": f"Your application has been {st.lower()}.", "project_id": project_id, "application_id": application_id, "outcome": st.lower(), "feedback": feedback})})
            except Exception:
                pass
        db.commit()
        # email student if known (project-specific template, not signup template)
        try:
            em = db.execute(text("SELECT email FROM user WHERE user_id = :sid"), {"sid": sid}).fetchone()
            st_row = db.execute(text("SELECT name FROM student WHERE student_id = :sid"), {"sid": sid}).fetchone()
            student_name = st_row.name if st_row and getattr(st_row, "name", None) else None
            fac_name = None
            if pj and getattr(pj, "faculty_id", None):
                fac_row = db.execute(text("SELECT name FROM faculty WHERE faculty_id = :fid"), {"fid": pj.faculty_id}).fetchone()
                fac_name = fac_row.name if fac_row and getattr(fac_row, "name", None) else None
            if em and em.email:
                send_application_decision_email(
                    to_email=em.email,
                    decision=st,
                    project_title=pj.title if pj and getattr(pj, "title", None) else None,
                    faculty_name=fac_name,
                    feedback=feedback,
                    student_name=student_name,
                )
        except Exception:
            pass
    return {"message": f"Application {st.lower()}. Student notified.", "project_id": project_id, "application_id": application_id, "status": st, "feedback": feedback}

def get_student_notifications(db: Session, student_id: int):
    _ensure_student_schema(db)
    try:
        rows = db.execute(text("SELECT notification_id, faculty_id, student_id, type, payload, status FROM notification WHERE student_id = :sid AND NOT (type IN ('StudentProfileChange','StudentAccountDeletion') AND status = 'Pending') ORDER BY notification_id DESC"), {"sid": student_id}).fetchall()
        out = []
        for r in rows:
            d = dict(r._mapping)
            out.append({"notification_id": d["notification_id"], "faculty_id": d.get("faculty_id"), "student_id": d.get("student_id"), "type": d["type"], "payload": d["payload"], "status": d["status"], "faculty_name": None})
        # fallback: legacy ApplicationDecision without student_id -> match payload student_id
        legacy = db.execute(text("SELECT notification_id, faculty_id, type, payload, status FROM notification WHERE type='ApplicationDecision' AND status='Pending'")).fetchall()
        for r in legacy:
            try:
                p = json.loads(r.payload)
                if int(p.get("student_id", -1)) == int(student_id):
                    if not any(x["notification_id"] == r.notification_id for x in out):
                        out.append({"notification_id": r.notification_id, "faculty_id": r.faculty_id, "student_id": student_id, "type": r.type, "payload": r.payload, "status": r.status, "faculty_name": None})
            except Exception:
                pass
        # profile change awaiting confirmation + results
        try:
            rows2 = db.execute(text("SELECT notification_id, faculty_id, student_id, type, payload, status FROM notification WHERE student_id = :sid AND ((type='StudentProfileChange' AND status='AwaitingStudentConfirmation') OR type IN ('StudentProfileChangeResult','StudentAccountDeletionResult')) ORDER BY notification_id DESC"), {"sid": student_id}).fetchall()
            for r in rows2:
                d = dict(r._mapping)
                if not any(x["notification_id"] == d["notification_id"] for x in out):
                    out.append({"notification_id": d["notification_id"], "faculty_id": d.get("faculty_id"), "student_id": d.get("student_id"), "type": d["type"], "payload": d["payload"], "status": d["status"], "faculty_name": None})
        except Exception:
            pass
        return out
    except Exception:
        # very old DB without student_id column
        rows = db.execute(text("SELECT notification_id, faculty_id, type, payload, status FROM notification WHERE type='ApplicationDecision'")).fetchall()
        out = []
        for r in rows:
            try:
                p = json.loads(r.payload)
                if int(p.get("student_id", -1)) == int(student_id):
                    out.append({"notification_id": r.notification_id, "faculty_id": r.faculty_id, "student_id": student_id, "type": r.type, "payload": r.payload, "status": r.status, "faculty_name": None})
            except Exception:
                pass
        return out

def ack_student_notification(db: Session, notification_id: int, student_id: int):
    n = db.execute(text("SELECT notification_id, payload, status, type FROM notification WHERE notification_id = :nid"), {"nid": notification_id}).fetchone()
    if not n:
        raise ValueError("Notification not found")
    db.execute(text("UPDATE notification SET status='Accepted' WHERE notification_id = :nid"), {"nid": notification_id})
    db.commit()
    return {"message": "Acknowledged"}

def handle_student_notification_response(db: Session, notification_id: int, student_id: int, action: str):
    _ensure_student_schema(db)
    try:
        n = db.execute(text("SELECT notification_id, student_id, type, payload, status FROM notification WHERE notification_id = :nid"), {"nid": notification_id}).fetchone()
    except Exception:
        n = db.execute(text("SELECT notification_id, type, payload, status FROM notification WHERE notification_id = :nid"), {"nid": notification_id}).fetchone()
    if not n:
        raise ValueError("Notification not found")
    d = dict(n._mapping)
    new_status = "Accepted" if str(action).lower().startswith("accept") else "Rejected"
    if d.get("type") in ("ApplicationDecision", "StudentProfileChangeResult", "StudentAccountDeletionResult"):
        db.execute(text("UPDATE notification SET status='Accepted' WHERE notification_id = :nid"), {"nid": notification_id})
        db.commit()
        return {"message": "Acknowledged"}
    if d.get("type") == "StudentProfileChange":
        if d.get("status") != "AwaitingStudentConfirmation":
            raise ValueError("Not awaiting your confirmation")
        if new_status == "Accepted":
            try:
                ch = json.loads(d.get("payload")).get("changes", {})
            except Exception:
                ch = {}
            if "cgpa" in ch:
                db.execute(text("UPDATE student SET cgpa = :v WHERE student_id = :sid"), {"v": ch["cgpa"]["new"], "sid": student_id})
            if "department" in ch:
                db.execute(text("UPDATE student SET department = :v WHERE student_id = :sid"), {"v": ch["department"]["new"], "sid": student_id})
            if "semester" in ch:
                db.execute(text("UPDATE student SET semester = :v WHERE student_id = :sid"), {"v": ch["semester"]["new"], "sid": student_id})
        db.execute(text("UPDATE notification SET status = :s WHERE notification_id = :nid"), {"s": new_status, "nid": notification_id})
        db.commit()
        # Tell the deciding admin (and only them) whether the student confirmed.
        try:
            try:
                _sch = json.loads(d.get("payload")).get("changes", {})
            except Exception:
                _sch = {}
            _summary = ("; ".join([f"{k}: {v.get('old')} → {v.get('new')}"
                                   for k, v in (_sch or {}).items()]) or "Profile change confirmation")
            try:
                _sn, _se = _student_contact(db, student_id)
            except Exception:
                _sn = None
            _email_response_to_originator(
                db, notification_id, "StudentProfileChange",
                f"Student {_sn or student_id}", new_status, _summary)
        except Exception:
            pass
        return {"message": f"Change {new_status.lower()}"}
    if d.get("type") == "AdminStudentEditRequest":
        if d.get("status") != "Pending":
            raise ValueError("This request has already been handled")
        if new_status == "Accepted":
            try:
                ch = json.loads(d.get("payload")).get("changes", {})
            except Exception:
                ch = {}
            field_map = {
                "name": "name",
                "cgpa": "cgpa",
                "department": "department",
                "semester": "semester",
                "github_link": "github_link",
                "cv_link": "cv_link"
            }
            for field, column in field_map.items():
                if field in ch:
                    db.execute(text(f"UPDATE student SET {column} = :value WHERE student_id = :sid"), {"value": ch[field]["new"], "sid": student_id})
            if "email" in ch:
                db.execute(text("UPDATE user SET email = :email WHERE user_id = :sid"), {"email": ch["email"]["new"], "sid": student_id})
                try:
                    _sync_credentials_email_only(student_id, ch["email"]["new"], "Student")
                except Exception:
                    pass
            if "skills" in ch:
                db.execute(text("DELETE FROM student_skills WHERE student_id = :sid"), {"sid": student_id})
                for sk in ch["skills"]["new"]:
                    db.execute(text("INSERT INTO student_skills (student_id, skill) VALUES (:sid, :sk)"), {"sid": student_id, "sk": sk})
            if "interests" in ch:
                db.execute(text("DELETE FROM student_interests WHERE student_id = :sid"), {"sid": student_id})
                for it in ch["interests"]["new"]:
                    db.execute(text("INSERT INTO student_interests (student_id, research_area) VALUES (:sid, :ra)"), {"sid": student_id, "ra": it})
        db.execute(text("UPDATE notification SET status = :s WHERE notification_id = :nid"), {"s": new_status, "nid": notification_id})
        db.commit()
        # Tell the proposing admin (and only them) how the student responded.
        try:
            _summary = ("; ".join([f"{k}: {v.get('old')} → {v.get('new')}"
                                   for k, v in (ch or {}).items()]) or "Profile update proposal")
            try:
                _sn, _se = _student_contact(db, student_id)
            except Exception:
                _sn = None
            _email_response_to_originator(
                db, notification_id, "AdminStudentEditRequest",
                f"Student {_sn or student_id}", new_status, _summary)
        except Exception:
            pass
        return {"message": f"Change {new_status.lower()}"}
    raise ValueError("Cannot respond here")


# ===========================================================================
# SUPERADMIN MODULE (single absolute authority, no approval chain)
# ===========================================================================
SUPERADMIN_ROLE = "superadmin"
SUPERADMIN_DEFAULT_EMAIL = "superadmin@uiu.ac.bd"


def _ensure_chat_table(db: Session):
    try:
        db.execute(text("""CREATE TABLE IF NOT EXISTS superadmin_chat (
            chat_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            admin_id INT NOT NULL,
            sender VARCHAR(20) NOT NULL,
            message TEXT NOT NULL,
            is_read TINYINT NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""))
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


def ensure_superadmin():
    """Create the single superadmin account if missing. Safe to call on startup."""
    from sqlalchemy import create_engine as _ce
    load_env_config()
    from database import DATABASE_URL as _IMPORTED_URL
    _URL = os.environ.get("DATABASE_URL", _IMPORTED_URL)
    email = os.environ.get("SUPERADMIN_EMAIL", SUPERADMIN_DEFAULT_EMAIL).strip()
    password = os.environ.get("SUPERADMIN_PASSWORD", "SuperAdmin#123")
    eng = _ce(_URL)
    with eng.connect() as conn:
        row = conn.execute(
            text("SELECT user_id, role FROM user WHERE LOWER(TRIM(email)) = :e"),
            {"e": email.lower()}).fetchone()
        if row:
            if str(row.role).strip().lower() != SUPERADMIN_ROLE:
                conn.execute(text("UPDATE user SET role = :r WHERE user_id = :u"),
                             {"r": SUPERADMIN_ROLE, "u": row.user_id})
                conn.commit()
            try:
                _append_credentials_json(int(row.user_id), email, SUPERADMIN_ROLE, None)
            except Exception:
                pass
            return int(row.user_id)
        conn.execute(
            text("INSERT INTO user (email, password, role) VALUES (:e, :p, :r)"),
            {"e": email, "p": hash_password(password), "r": SUPERADMIN_ROLE})
        conn.commit()
        row = conn.execute(
            text("SELECT user_id FROM user WHERE LOWER(TRIM(email)) = :e"),
            {"e": email.lower()}).fetchone()
        try:
            _append_credentials_json(int(row.user_id), email, SUPERADMIN_ROLE, password)
        except Exception:
            pass
        print(f"[SUPERADMIN] Seeded superadmin account: {email}")
        return int(row.user_id)


def _sa_actor(db: Session, actor_id: int):
    row = db.execute(text("SELECT user_id, email, role FROM user WHERE user_id = :u"),
                     {"u": actor_id}).fetchone()
    if not row or str(row.role).strip().lower() != SUPERADMIN_ROLE:
        raise ValueError("Superadmin access required.")
    return row


def _sa_verify_password(db: Session, actor_id: int, current_password):
    """Every superadmin mutation (edit/create/delete) needs own password."""
    row = db.execute(text("SELECT password FROM user WHERE user_id = :u"),
                     {"u": actor_id}).fetchone()
    if not row or not verify_password(current_password or "", row.password):
        raise ValueError("Incorrect current password. Enter YOUR superadmin password to confirm.")


def _fmt_val(v):
    if v is None:
        return "—"
    if isinstance(v, list):
        return ", ".join(str(x) for x in v) if v else "—"
    s = str(v).strip()
    return s if s != "" else "—"


def _diff_lines(pairs):
    """pairs: list of (label, old, new). Returns human-readable change lines."""
    lines = []
    for label, old, new in pairs:
        if str(old or "") != str(new or "") and new is not None and str(new).strip() != "":
            lines.append(f"{label}: {_fmt_val(old)} → {_fmt_val(new)}")
    return lines


def _sa_target_user(db: Session, target_id: int):
    row = db.execute(text("SELECT user_id, email, role FROM user WHERE user_id = :u"),
                     {"u": target_id}).fetchone()
    if not row:
        raise ValueError("User not found.")
    if str(row.role).strip().lower() == SUPERADMIN_ROLE:
        raise ValueError("The superadmin account cannot be modified here.")
    return row


def _sa_audit(db: Session, actor_id: int, action: str, target_type: str,
              target_id, detail: str = ""):
    _ensure_student_schema(db)
    payload = json.dumps({
        "actor_id": int(actor_id),
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "detail": detail or "",
    })
    try:
        db.execute(text("INSERT INTO notification (faculty_id, student_id, type, payload, status)"
                        " VALUES (NULL, NULL, 'SuperAdminAction', :p, 'Accepted')"), {"p": payload})
    except Exception:
        db.rollback()
        db.execute(text("INSERT INTO notification (faculty_id, type, payload, status)"
                        " VALUES (NULL, 'SuperAdminAction', :p, 'Accepted')"), {"p": payload})
    db.commit()


ADMIN_ACTIVITY_TYPE = "AdminActivity"


def _log_admin_activity(db: Session, admin_id, action: str, notification_id=None,
                        notification_type=None, detail: str = "", snapshot=None):
    """Permanent mirror of every admin action for the superadmin.

    Stored as a notification row with type='AdminActivity' and status='Accepted'
    so it NEVER appears in any Pending queue and is NEVER deleted by the
    normal accept/reject flow. Best-effort: never breaks the main action.
    """
    try:
        if admin_id is None:
            return False
        try:
            aid = int(admin_id)
        except (TypeError, ValueError):
            return False
        admin_email = ""
        try:
            arow = db.execute(text("SELECT email, role FROM user WHERE user_id = :u"),
                              {"u": aid}).fetchone()
            if arow:
                admin_email = getattr(arow, "email", "") or ""
        except Exception:
            pass
        safe_snapshot = None
        try:
            if snapshot is not None:
                s = dict(snapshot) if isinstance(snapshot, dict) else {"value": str(snapshot)}
                if isinstance(s, dict) and "password" in s:
                    s.pop("password", None)
                    s["password_scrubbed"] = True
                safe_snapshot = s
        except Exception:
            safe_snapshot = None
        payload = json.dumps({
            "actor_id": aid,
            "actor_role": "admin",
            "admin_email": admin_email,
            "action": action,
            "notification_id": notification_id,
            "notification_type": notification_type,
            "detail": detail or "",
            "snapshot": safe_snapshot,
        })
        try:
            db.execute(text("INSERT INTO notification (faculty_id, student_id, type, payload, status)"
                            " VALUES (NULL, NULL, 'AdminActivity', :p, 'Accepted')"), {"p": payload})
        except Exception:
            db.execute(text("INSERT INTO notification (faculty_id, type, payload, status)"
                            " VALUES (NULL, 'AdminActivity', :p, 'Accepted')"), {"p": payload})
        return True
    except Exception as e:
        print(f"[ADMIN ACTIVITY LOG] Could not mirror admin action: {e}")
        return False


def send_info_email(to_email: str, subject: str, body_text: str):
    """Short administrative notice email (plain notice, no OTP box)."""
    if not to_email:
        return False
    load_env_config()
    sender_email = os.environ.get("GMAIL_SENDER_EMAIL", "").strip()
    sender_password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    html_content = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 520px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff; color: #1e293b;">
        <div style="text-align: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid #e2e8f0;">
            <h1 style="color: #1e3a8a; margin: 0; font-size: 22px; font-weight: 700;">United International University</h1>
            <p style="color: #64748b; margin: 4px 0 0 0; font-size: 14px;">Research Management Portal</p>
        </div>
        <h2 style="margin: 0 0 12px 0; font-size: 18px;">{subject}</h2>
        <p style="font-size: 14px; color: #334155; line-height: 1.6;">{body_text}</p>
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0 16px 0;">
        <p style="font-size: 12px; color: #94a3b8; text-align: center; margin: 0;">Sent by Research Management Portal to {to_email}</p>
    </div>
    """
    email_sent = False
    if sender_email and sender_password and mail_sending_enabled():
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"United International University Research Portal <{sender_email}>"
            msg["To"] = to_email
            msg["Reply-To"] = sender_email
            msg["Date"] = formatdate(localtime=True)
            msg.attach(MIMEText(body_text, "plain"))
            msg.attach(MIMEText(html_content, "html"))
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, [to_email], msg.as_string())
            email_sent = True
        except Exception as e:
            print(f"[INFO EMAIL ERROR] {e}")
    print(f"[INFO EMAIL] To {to_email}: {subject} ({'sent' if email_sent else 'console only'})")
    return email_sent


def superadmin_update_faculty(db: Session, actor_id: int, faculty_id: int, edit):
    _sa_actor(db, actor_id)
    _sa_verify_password(db, actor_id, getattr(edit, "current_password", None))
    target = _sa_target_user(db, faculty_id)
    if str(target.role).strip().lower() != "faculty":
        raise ValueError("Target user is not a faculty member.")
    old = get_faculty_by_id(db=db, faculty_id=faculty_id)
    if not old:
        raise ValueError("Faculty not found.")
    if edit.email and _email_taken(db, edit.email, exclude_id=faculty_id):
        raise ValueError("This email address is already registered.")
    old_areas = sorted([(a.get("research_area") if isinstance(a, dict) else a)
                        for a in (old.get("research_areas") or [])])
    new_areas = sorted(edit.research_areas) if edit.research_areas is not None else old_areas
    changes = _diff_lines([
        ("Name", old.get("name"), edit.name),
        ("Email", old.get("email"), edit.email),
        ("Designation", old.get("designation"), edit.designation),
        ("Department", old.get("department"), edit.department),
        ("Office Hours", old.get("office_hours"), edit.office_hours),
        ("Research Areas", old_areas, new_areas if edit.research_areas is not None else None),
    ])
    if not changes:
        raise ValueError("No changes were detected.")
    if edit.name is not None:
        db.execute(text("UPDATE faculty SET name = :v WHERE faculty_id = :f"),
                   {"v": edit.name, "f": faculty_id})
    if edit.designation is not None:
        db.execute(text("UPDATE faculty SET designation = :v WHERE faculty_id = :f"),
                   {"v": edit.designation, "f": faculty_id})
    if edit.department is not None:
        db.execute(text("UPDATE faculty SET department = :v WHERE faculty_id = :f"),
                   {"v": edit.department, "f": faculty_id})
    if edit.office_hours is not None:
        db.execute(text("UPDATE faculty SET office_hours = :v WHERE faculty_id = :f"),
                   {"v": edit.office_hours, "f": faculty_id})
    if edit.email:
        db.execute(text("UPDATE user SET email = :e WHERE user_id = :u"),
                   {"e": edit.email, "u": faculty_id})
    if edit.research_areas is not None:
        db.execute(text("DELETE FROM faculty_research_areas WHERE faculty_id = :f"),
                   {"f": faculty_id})
        for area in edit.research_areas or []:
            db.execute(text("INSERT INTO faculty_research_areas (faculty_id, research_area)"
                            " VALUES (:f, :a)"), {"f": faculty_id, "a": area})
    db.commit()
    final_email = edit.email or target.email
    _append_credentials_json(faculty_id, final_email, "Faculty", None)
    detail = "; ".join(changes)
    _sa_audit(db, actor_id, "faculty_edit", "faculty", faculty_id, detail)
    try:
        send_info_email(final_email, "Your profile was updated by administration",
                        "The portal superadmin changed the following on your faculty profile: "
                        + detail + ". If anything looks wrong, please contact administration.")
    except Exception:
        pass
    return get_faculty_by_id(db=db, faculty_id=faculty_id)


def superadmin_update_student(db: Session, actor_id: int, student_id: int, edit):
    _sa_actor(db, actor_id)
    _sa_verify_password(db, actor_id, getattr(edit, "current_password", None))
    target = _sa_target_user(db, student_id)
    if str(target.role).strip().lower() != "student":
        raise ValueError("Target user is not a student.")
    old = get_student_by_id(db=db, student_id=student_id)
    if not old:
        raise ValueError("Student not found.")
    _ensure_student_schema(db)
    if edit.email and _email_taken(db, edit.email, exclude_id=student_id):
        raise ValueError("This email address is already registered.")
    if edit.cgpa is not None and str(edit.cgpa).strip() != "" and not _valid_cgpa(edit.cgpa):
        raise ValueError("CGPA must be between 0.00 and 4.00 (up to 2 decimals)")
    _validate_student_contact_fields(email=edit.email, github_link=edit.github_link,
                                     cv_link=edit.cv_link)
    if edit.github_link is not None and str(edit.github_link).strip() != "" \
            and _student_link_taken(db, "github", edit.github_link, exclude_id=student_id):
        raise ValueError("This GitHub link is already in use.")
    if edit.cv_link is not None and str(edit.cv_link).strip() != "" \
            and _student_link_taken(db, "cv", edit.cv_link, exclude_id=student_id):
        raise ValueError("This CV link is already in use.")
    db.execute(text("UPDATE student SET name = COALESCE(:n, name), cgpa = COALESCE(:c, cgpa),"
                    " department = COALESCE(:d, department), semester = COALESCE(:s, semester),"
                    " github_link = COALESCE(:g, github_link), cv_link = COALESCE(:v, cv_link)"
                    " WHERE student_id = :sid"),
               {"n": edit.name, "c": edit.cgpa, "d": edit.department, "s": edit.semester,
                "g": edit.github_link, "v": edit.cv_link, "sid": student_id})
    if edit.email:
        db.execute(text("UPDATE user SET email = :e WHERE user_id = :u"),
                   {"e": edit.email, "u": student_id})
    if edit.skills is not None:
        db.execute(text("DELETE FROM student_skills WHERE student_id = :sid"), {"sid": student_id})
        for sk in edit.skills or []:
            try:
                db.execute(text("INSERT INTO student_skills (student_id, skill) VALUES (:sid, :sk)"),
                           {"sid": student_id, "sk": sk})
            except Exception:
                pass
    if edit.interests is not None:
        try:
            db.execute(text("DELETE FROM student_interests WHERE student_id = :sid"), {"sid": student_id})
            for it in edit.interests or []:
                try:
                    db.execute(text("INSERT INTO student_interests (student_id, research_area)"
                                    " VALUES (:sid, :ra)"), {"sid": student_id, "ra": it})
                except Exception:
                    pass
        except Exception:
            pass
    db.commit()
    final_email = edit.email or target.email
    changes = _diff_lines([
        ("Name", old.get("name"), edit.name),
        ("Email", old.get("email"), edit.email),
        ("CGPA", old.get("cgpa"), edit.cgpa),
        ("Department", old.get("department"), edit.department),
        ("Semester", old.get("semester"), edit.semester),
        ("GitHub Link", old.get("github_link"), edit.github_link),
        ("CV Link", old.get("cv_link"), edit.cv_link),
        ("Skills", old.get("skills") or [], edit.skills),
        ("Research Interests", old.get("interests") or [], edit.interests),
    ])
    if not changes:
        raise ValueError("No changes were detected.")
    _append_credentials_json(student_id, final_email, "Student", None)
    detail = "; ".join(changes)
    _sa_audit(db, actor_id, "student_edit", "student", student_id, detail)
    try:
        send_info_email(final_email, "Your profile was updated by administration",
                        "The portal superadmin changed the following on your student profile: "
                        + detail + ". If anything looks wrong, please contact administration.")
    except Exception:
        pass
    return get_student_by_id(db=db, student_id=student_id)


def superadmin_update_admin(db: Session, actor_id: int, target_id: int, edit):
    _sa_actor(db, actor_id)
    _sa_verify_password(db, actor_id, getattr(edit, "current_password", None))
    target = _sa_target_user(db, target_id)
    if str(target.role).strip().lower() != "admin":
        raise ValueError("Target user is not an admin.")
    if not edit.email or str(edit.email).strip() == "":
        raise ValueError("Provide the new email.")
    if str(edit.email).strip().lower() == str(target.email).strip().lower():
        raise ValueError("No changes were detected.")
    if _email_taken(db, edit.email, exclude_id=target_id):
        raise ValueError("This email address is already registered.")
    db.execute(text("UPDATE user SET email = :e WHERE user_id = :u"),
               {"e": edit.email, "u": target_id})
    db.commit()
    _append_credentials_json(target_id, edit.email, "admin", None)
    detail = f"Email: {target.email} → {edit.email}"
    _sa_audit(db, actor_id, "admin_edit", "admin", target_id, detail)
    try:
        send_info_email(edit.email, "Your admin profile was updated",
                        "The portal superadmin changed your administrator account: "
                        + detail + ".")
    except Exception:
        pass
    return get_admin_by_id(db=db, admin_id=target_id)


def superadmin_update_self(db: Session, actor_id: int, email=None, current_password=None,
                           new_password=None):
    me = _sa_actor(db, actor_id)
    if not current_password:
        raise ValueError("Current password is required for any change.")
    if not verify_password(current_password, db.execute(
            text("SELECT password FROM user WHERE user_id = :u"),
            {"u": actor_id}).fetchone().password):
        raise ValueError("Incorrect current password.")
    if email and _email_taken(db, email, exclude_id=actor_id):
        raise ValueError("This email address is already registered.")
    if new_password:
        if len(new_password) < 6:
            raise ValueError("New password must be at least 6 characters.")
        db.execute(text("UPDATE user SET password = :p WHERE user_id = :u"),
                   {"p": hash_password(new_password), "u": actor_id})
    if email:
        db.execute(text("UPDATE user SET email = :e WHERE user_id = :u"),
                   {"e": email, "u": actor_id})
    db.commit()
    row = db.execute(text("SELECT email FROM user WHERE user_id = :u"),
                     {"u": actor_id}).fetchone()
    _append_credentials_json(actor_id, row.email if row else me.email,
                             SUPERADMIN_ROLE, new_password)
    return {"user_id": actor_id, "email": row.email if row else me.email, "role": SUPERADMIN_ROLE}


def superadmin_delete_user(db: Session, actor_id: int, target_id: int, current_password=None):
    _sa_actor(db, actor_id)
    _sa_verify_password(db, actor_id, current_password)
    if int(target_id) == int(actor_id):
        raise ValueError("You cannot delete your own superadmin account.")
    target = _sa_target_user(db, target_id)
    try:
        send_info_email(target.email, "Your portal account was removed",
                        "Your Research Management Portal account was removed by the superadmin. "
                        "Contact administration if you believe this is a mistake.")
    except Exception:
        pass
    db.execute(text("DELETE FROM user WHERE user_id = :u"), {"u": target_id})
    db.commit()
    try:
        _remove_credentials_json(target_id)
    except Exception:
        pass
    _sa_audit(db, actor_id, "user_delete", str(target.role), target_id,
              f"Deleted {target.role} ({target.email}) with cascade.")
    return {"message": f"{target.role} account deleted with all related data."}


def superadmin_create_project(db: Session, actor_id: int, title: str, description=None,
                              required_skill=None, status="Active", faculty_id=None,
                              current_password=None):
    _sa_actor(db, actor_id)
    _sa_verify_password(db, actor_id, current_password)
    fac = db.execute(text("SELECT faculty_id FROM faculty WHERE faculty_id = :f"),
                     {"f": faculty_id}).fetchone()
    if not fac:
        raise ValueError("Faculty not found.")
    db.execute(text("INSERT INTO research_project (faculty_id, title, description, required_skill, status)"
                    " VALUES (:f, :t, :d, :s, :st)"),
               {"f": faculty_id, "t": title, "d": description, "s": required_skill,
                "st": status or "Active"})
    db.commit()
    new_id = db.execute(text("SELECT project_id FROM research_project WHERE faculty_id = :f"
                             " ORDER BY project_id DESC LIMIT 1"), {"f": faculty_id}).fetchone().project_id
    # Inform the owning faculty: in-app notification (Pending until acknowledged) + email.
    fac_email = ""
    try:
        fac_info = get_faculty_by_id(db=db, faculty_id=faculty_id)
        fac_email = (fac_info.get("email") if fac_info else "") or ""
    except Exception:
        pass
    try:
        creation_payload = json.dumps({
            "message": f"The superadmin has directly created the project '{title}' under your supervision.",
            "outcome": "accepted",
            "title": title,
            "source": "superadmin_direct",
        })
        db.execute(text("INSERT INTO notification (faculty_id, type, payload, status)"
                        " VALUES (:f, 'ProjectCreationResult', :p, 'Pending')"),
                   {"f": faculty_id, "p": creation_payload})
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    _sa_audit(db, actor_id, "project_create", "project", int(new_id),
              f"Created '{title}' for faculty {faculty_id}.")
    try:
        if fac_email:
            send_info_email(fac_email, f"New project assigned: '{title}'",
                            f"The portal superadmin has created a new research project '{title}' "
                            f"under your supervision. Please check your Notification Hub.")
    except Exception:
        pass
    return get_project_by_id(db=db, project_id=int(new_id))


def superadmin_update_project(db: Session, actor_id: int, project_id: int, edit):
    _sa_actor(db, actor_id)
    _sa_verify_password(db, actor_id, getattr(edit, "current_password", None))
    proj = get_project_by_id(db=db, project_id=project_id)
    if not proj:
        raise ValueError("Project not found.")
    if edit.faculty_id is not None:
        fac = db.execute(text("SELECT faculty_id FROM faculty WHERE faculty_id = :f"),
                         {"f": edit.faculty_id}).fetchone()
        if not fac:
            raise ValueError("Faculty not found.")
        db.execute(text("UPDATE research_project SET faculty_id = :f WHERE project_id = :p"),
                   {"f": edit.faculty_id, "p": project_id})
    db.execute(text("UPDATE research_project SET title = COALESCE(:t, title),"
                    " description = COALESCE(:d, description),"
                    " required_skill = COALESCE(:s, required_skill),"
                    " status = COALESCE(:st, status) WHERE project_id = :p"),
               {"t": edit.title, "d": edit.description, "s": edit.required_skill,
                "st": edit.status, "p": project_id})
    db.commit()
    changes = _diff_lines([
        ("Title", proj.get("title"), edit.title),
        ("Description", proj.get("description"), edit.description),
        ("Required Skill", proj.get("required_skill"), edit.required_skill),
        ("Status", proj.get("status"), edit.status),
    ])
    # Inform the owning faculty (in-app + email) — previously silent.
    try:
        _final = get_project_by_id(db=db, project_id=project_id)
        _owner_fid = (_final.get("faculty_id") if _final else None) or proj.get("faculty_id")
        _change_text = ("; ".join(changes)) if changes else "Project details updated"
        try:
            update_payload = json.dumps({
                "message": f"The superadmin has updated your project '{proj.get('title')}'.",
                "outcome": "accepted",
                "title": (_final.get("title") if _final else None) or proj.get("title"),
                "changes": _change_text,
                "source": "superadmin_direct",
            })
            db.execute(text("INSERT INTO notification (faculty_id, type, payload, status)"
                            " VALUES (:f, 'SuperAdminProjectUpdate', :p, 'Pending')"),
                       {"f": _owner_fid, "p": update_payload})
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
        try:
            _fn, _femail = _faculty_contact(db, _owner_fid)
            if _femail:
                try:
                    send_info_email(
                        _femail, f"Your project was updated: '{proj.get('title')}'",
                        f"The portal superadmin has updated your research project. Changes: "
                        f"{_change_text}. Please check your Notification Hub.")
                except Exception:
                    pass
        except Exception:
            pass
    except Exception:
        pass
    _sa_audit(db, actor_id, "project_edit", "project", project_id,
              ("; ".join(changes)) if changes else "Direct project edit (supervisor/faculty reassigned or no field changes).")
    return get_project_by_id(db=db, project_id=project_id)


def superadmin_delete_project(db: Session, actor_id: int, project_id: int, current_password=None):
    _sa_actor(db, actor_id)
    _sa_verify_password(db, actor_id, current_password)
    proj = get_project_by_id(db=db, project_id=project_id)
    if not proj:
        raise ValueError("Project not found.")
    owner_fid = proj.get("faculty_id")
    owner_email = ""
    try:
        owner_row = db.execute(text("SELECT email FROM user WHERE user_id = :u"),
                               {"u": owner_fid}).fetchone()
        owner_email = (owner_row.email if owner_row else "") or ""
    except Exception:
        pass
    db.execute(text("DELETE FROM research_project WHERE project_id = :p"), {"p": project_id})
    db.commit()
    # Inform the owning faculty: in-app notification (Pending until acknowledged) + email.
    try:
        deletion_payload = json.dumps({
            "message": f"The superadmin has deleted your project '{proj['title']}'.",
            "outcome": "accepted",
            "title": proj["title"],
            "source": "superadmin_direct",
        })
        db.execute(text("INSERT INTO notification (faculty_id, type, payload, status)"
                        " VALUES (:f, 'ProjectDeletionResult', :p, 'Pending')"),
                   {"f": owner_fid, "p": deletion_payload})
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    _sa_audit(db, actor_id, "project_delete", "project", project_id,
              f"Deleted '{proj['title']}' with its applications.")
    try:
        if owner_email:
            send_info_email(owner_email, f"Project deleted: '{proj['title']}'",
                            f"The portal superadmin has deleted the research project '{proj['title']}' "
                            f"along with its applications. Please check your Notification Hub.")
    except Exception:
        pass
    return {"message": "Project deleted with all its applications."}


def get_audit_log(db: Session, actor_id: int, limit: int = 100):
    _sa_actor(db, actor_id)
    rows = db.execute(text("SELECT notification_id, type, payload, status, created_at"
                           " FROM notification WHERE type IN ('SuperAdminAction', 'AdminActivity')"
                           " ORDER BY notification_id DESC LIMIT :lim"), {"lim": limit}).fetchall()
    out = []
    for r in rows:
        try:
            data = json.loads(r.payload)
        except Exception:
            data = {"detail": r.payload}
        if str(getattr(r, "type", "")) == "AdminActivity":
            out.append({
                "notification_id": r.notification_id,
                "type": r.type,
                "status": r.status,
                "created_at": str(r.created_at) if hasattr(r, "created_at") and r.created_at else None,
                "action": f"admin_{data.get('action', 'activity')}",
                "target_type": "notification",
                "target_id": data.get("notification_id"),
                "detail": (f"Admin {data.get('admin_email') or data.get('actor_id')} — "
                           f"{data.get('notification_type', '')} {data.get('action', '')}: "
                           f"{data.get('detail', '')}").strip(),
                "actor_id": data.get("actor_id"),
                "admin_email": data.get("admin_email"),
                "notification_type": data.get("notification_type"),
                "is_admin_activity": True,
            })
        else:
            out.append({
                "notification_id": r.notification_id,
                "type": r.type,
                "status": r.status,
                "created_at": str(r.created_at) if hasattr(r, "created_at") and r.created_at else None,
                "action": data.get("action"),
                "target_type": data.get("target_type"),
                "target_id": data.get("target_id"),
                "detail": data.get("detail"),
                "actor_id": data.get("actor_id"),
                "is_admin_activity": False,
            })
    return out


def get_admin_activity_log(db: Session, actor_id: int, limit: int = 200):
    """Permanent record of every admin action, visible only to the superadmin."""
    _sa_actor(db, actor_id)
    try:
        lmt = max(1, min(int(limit), 500))
    except Exception:
        lmt = 200
    rows = db.execute(text("SELECT notification_id, type, payload, status, created_at"
                           " FROM notification WHERE type = 'AdminActivity'"
                           " ORDER BY notification_id DESC LIMIT :lim"), {"lim": lmt}).fetchall()
    out = []
    for r in rows:
        try:
            data = json.loads(r.payload)
        except Exception:
            data = {}
        out.append({
            "notification_id": r.notification_id,
            "type": r.type,
            "status": r.status,
            "created_at": str(r.created_at) if hasattr(r, "created_at") and r.created_at else None,
            "action": data.get("action"),
            "admin_id": data.get("actor_id"),
            "admin_email": data.get("admin_email"),
            "target_notification_id": data.get("notification_id"),
            "notification_type": data.get("notification_type"),
            "detail": data.get("detail"),
            "snapshot": data.get("snapshot"),
        })
    return out


# ---- SuperAdmin <-> Admin channel ----
def chat_send(db: Session, admin_id: int, sender: str, message: str):
    _ensure_chat_table(db)
    sender = str(sender or "").strip().lower()
    if sender not in ("admin", "superadmin"):
        raise ValueError("Invalid sender.")
    admin = db.execute(text("SELECT user_id, role FROM user WHERE user_id = :u"),
                       {"u": admin_id}).fetchone()
    if not admin or str(admin.role).strip().lower() != "admin":
        raise ValueError("Chat channel exists only for admin accounts.")
    text_msg = str(message or "").strip()
    if not text_msg:
        raise ValueError("Message cannot be empty.")
    if len(text_msg) > 2000:
        raise ValueError("Message too long (max 2000 characters).")
    db.execute(text("INSERT INTO superadmin_chat (admin_id, sender, message, is_read)"
                    " VALUES (:a, :s, :m, 0)"),
               {"a": admin_id, "s": sender, "m": text_msg})
    db.commit()
    # Email the other side of this 1:1 channel about the new message.
    try:
        _excerpt = text_msg if len(text_msg) <= 300 else text_msg[:300] + "…"
        if sender == "admin":
            _sa = db.execute(text("SELECT email FROM user WHERE role = 'superadmin' LIMIT 1")).fetchone()
            _to = (_sa.email if _sa else "") or ""
            _label = "an administrator"
        else:
            _ad = db.execute(text("SELECT email FROM user WHERE user_id = :u"), {"u": admin_id}).fetchone()
            _to = (_ad.email if _ad else "") or ""
            _label = "the superadmin"
        if _to:
            try:
                send_admin_notice_email(
                    to_email=_to,
                    title="New Message in Admin Channel",
                    intro=f"You have a new message from {_label}. Please open the admin channel to read and reply.",
                    details=[("Message", _excerpt)],
                    next_step="Open the Super Admin Channel in the portal to reply.",
                    tone="info")
            except Exception:
                pass
    except Exception:
        pass
    return {"message": "Message sent."}


def chat_thread(db: Session, admin_id: int):
    _ensure_chat_table(db)
    rows = db.execute(text("SELECT chat_id, admin_id, sender, message, is_read, created_at"
                           " FROM superadmin_chat WHERE admin_id = :a ORDER BY chat_id ASC"),
                      {"a": admin_id}).fetchall()
    return [{
        "chat_id": r.chat_id,
        "admin_id": r.admin_id,
        "sender": r.sender,
        "message": r.message,
        "is_read": bool(r.is_read),
        "created_at": str(r.created_at) if r.created_at else None,
    } for r in rows]


def chat_unread_for_superadmin(db: Session):
    _ensure_chat_table(db)
    rows = db.execute(text("SELECT admin_id, COUNT(*) AS c FROM superadmin_chat"
                           " WHERE sender = 'admin' AND is_read = 0 GROUP BY admin_id")).fetchall()
    counts = {int(r.admin_id): int(r.c) for r in rows}
    admins = db.execute(text("SELECT user_id, email FROM user WHERE role = 'admin'")).fetchall()
    return [{"admin_id": a.user_id, "email": a.email,
             "unread": int(counts.get(int(a.user_id), 0))} for a in admins]


def chat_unread_for_admin(db: Session, admin_id: int):
    _ensure_chat_table(db)
    row = db.execute(text("SELECT COUNT(*) AS c FROM superadmin_chat"
                          " WHERE admin_id = :a AND sender = 'superadmin' AND is_read = 0"),
                     {"a": admin_id}).fetchone()
    return {"unread": int(row.c) if row else 0}


def chat_mark_read(db: Session, admin_id: int, reader: str, message_ids=None):
    _ensure_chat_table(db)
    reader = str(reader or "").strip().lower()
    other = "superadmin" if reader == "admin" else "admin"
    if message_ids:
        ids = [int(x) for x in message_ids]
        if not ids:
            return {"updated": 0}
        placeholders = ",".join([f":id{i}" for i in range(len(ids))])
        params = {"a": admin_id, "s": other}
        params.update({f"id{i}": v for i, v in enumerate(ids)})
        res = db.execute(text(f"UPDATE superadmin_chat SET is_read = 1 WHERE admin_id = :a"
                              f" AND sender = :s AND chat_id IN ({placeholders})"), params)
    else:
        res = db.execute(text("UPDATE superadmin_chat SET is_read = 1 WHERE admin_id = :a"
                              " AND sender = :s"), {"a": admin_id, "s": other})
    db.commit()
    try:
        return {"updated": int(res.rowcount or 0)}
    except Exception:
        return {"updated": 0}


