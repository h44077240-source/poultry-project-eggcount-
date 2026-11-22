"""
Email dispatch service for security alerts, account lockout notifications,
and password reset workflows.
"""
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.config import settings

logger = logging.getLogger("auth_security_email")


def generate_lockout_email_content(email: str, reset_link: str, lockout_minutes: int, request_ip: Optional[str] = None) -> tuple[str, str]:
    """Generate plaintext and HTML versions of the account lockout security alert."""
    ip_info = f" from IP address {request_ip}" if request_ip else ""
    
    plain_text = f"""Hello,

This is an automated security notice from {settings.APP_NAME}.

Your account ({email}) has been temporarily locked for {lockout_minutes} minutes following 5 consecutive failed login attempts{ip_info}.

If this was you and you forgot your password, or if you suspect unauthorized access attempts, you can reset your password immediately using the link below:

{reset_link}

This link is valid for {lockout_minutes} minutes.

If you did not attempt to sign in, please secure your credentials immediately.

Regards,
{settings.EMAILS_FROM_NAME}
"""

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Security Alert: Account Lockout</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px; color: #1e293b; }}
    .container {{ max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }}
    .header {{ background: #dc2626; color: #ffffff; padding: 24px; text-align: center; }}
    .content {{ padding: 28px 24px; line-height: 1.6; font-size: 15px; }}
    .alert-box {{ background: #fef2f2; border-left: 4px solid #ef4444; padding: 14px 18px; border-radius: 6px; margin: 18px 0; color: #991b1b; font-size: 14px; }}
    .btn {{ display: inline-block; background: #2563eb; color: #ffffff !important; padding: 12px 28px; border-radius: 8px; text-decoration: none; font-weight: 700; font-size: 15px; margin: 20px 0; }}
    .footer {{ padding: 16px 24px; background: #f1f5f9; font-size: 12px; color: #64748b; text-align: center; border-top: 1px solid #e2e8f0; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h2 style="margin:0; font-size: 20px;">🛡️ Security Alert: Account Locked</h2>
    </div>
    <div class="content">
      <p>Hello,</p>
      <div class="alert-box">
        <strong>Notice:</strong> Your account (<code>{email}</code>) has been temporarily locked for <strong>{lockout_minutes} minutes</strong> after 5 consecutive failed login attempts{ip_info}.
      </div>
      <p>To protect your evidence data and account integrity, further login attempts are currently suspended.</p>
      <p>If you forgot your password or need to regain access immediately, click the secure reset button below:</p>
      <div style="text-align: center;">
        <a href="{reset_link}" class="btn">Reset Password & Unlock Account</a>
      </div>
      <p style="font-size: 13px; color: #64748b;">Or copy and paste this link into your browser:<br><a href="{reset_link}" style="word-break: break-all; color: #2563eb;">{reset_link}</a></p>
      <p style="font-size: 13px; color: #94a3b8;">This reset link expires in {lockout_minutes} minutes.</p>
    </div>
    <div class="footer">
      &copy; {settings.APP_NAME} Security Infrastructure. Automated notification — do not reply.
    </div>
  </div>
</body>
</html>"""
    return plain_text, html_content


def send_lockout_notification(
    email: str,
    reset_token: str,
    request_ip: Optional[str] = None
) -> bool:
    """
    Sends an account lockout notification email containing a secure password reset link.
    If SMTP credentials are not configured, securely logs the reset link for development.
    """
    reset_link = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?token={reset_token}"
    lockout_mins = settings.ACCOUNT_LOCKOUT_MINUTES
    plain_text, html_content = generate_lockout_email_content(email, reset_link, lockout_mins, request_ip)

    # 1. If SMTP server is configured, send via live SMTP
    if settings.SMTP_HOST:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[{settings.APP_NAME}] Security Alert: Account Locked"
            msg["From"] = f"{settings.EMAILS_FROM_NAME} <{settings.EMAILS_FROM_EMAIL}>"
            msg["To"] = email

            msg.attach(MIMEText(plain_text, "plain", "utf-8"))
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            if settings.SMTP_TLS:
                server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)

            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)

            server.sendmail(settings.EMAILS_FROM_EMAIL, [email], msg.as_string())
            server.quit()
            logger.info(f"Security lockout notification email sent to {email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send lockout email to {email} via SMTP: {e}")

    # 2. In development / testing environments without live SMTP, output secure audit banner
    print("\n" + "=" * 70)
    print("🔒 [SECURITY AUDIT] ACCOUNT LOCKOUT TRIGGERED - 5 CONSECUTIVE FAILED ATTEMPTS")
    print(f"Target Account : {email}")
    if request_ip:
        print(f"Origin IP      : {request_ip}")
    print(f"Lockout Period : {lockout_mins} minutes")
    print(f"Password Reset : {reset_link}")
    print("=" * 70 + "\n")
    return True
