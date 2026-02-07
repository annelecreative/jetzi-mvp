# navora_test_email.py
import os
import smtplib
from email.mime.text import MIMEText

from dotenv import load_dotenv

APP_NAME = "lalyfe"

load_dotenv()

EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_SMTP_HOST = os.getenv("EMAIL_SMTP_HOST", "smtp.sendgrid.net")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")


def send_test_email():
    if not (EMAIL_FROM and EMAIL_TO and EMAIL_USERNAME and EMAIL_PASSWORD):
        print("Email not configured properly. Check your .env.")
        return

    subject = f"[{APP_NAME}] Test email from SendGrid setup"
    body = "If you see this, your Navora + SendGrid configuration is working. 🎉"

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    try:
        with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            server.send_message(msg)
        print(f"✅ Test email sent to {EMAIL_TO}")
    except Exception as e:
        print(f"❌ Failed to send test email: {e}")


if __name__ == "__main__":
    send_test_email()
