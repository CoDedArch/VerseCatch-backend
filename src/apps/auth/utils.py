import sendgrid
from sendgrid.helpers.mail import Mail, From, To, Subject, HtmlContent
from core.config import settings
import hmac
from passlib.context import CryptContext
import hashlib
from fastapi import HTTPException
from datetime import datetime, timedelta
from typing import Dict, Any
from jose import jwt
import logging

# Configure logging
logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")



def get_password_hash(password: str) -> str:
    """Hash a plaintext password"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against the hashed version"""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: Dict[str, Any], expires_delta: timedelta = None) -> str:
    """Create an access token for authenticated users"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def create_verification_token(data: Dict[str, Any], expires_delta: timedelta = None) -> str:
    """Create a JWT verification token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)  # Default 15 min expiration for verification
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def send_verification_email(email: str, token: str):
    """
    Send a production-ready verification email using SendGrid
    """
    verification_url = f"https://9350-129-224-201-60.ngrok-free.app/auth/verify?token={token}"
    
    # Professional email template with plain text fallback
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Verify Your VerseCatch Account</title>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .button {{
                display: inline-block;
                padding: 12px 24px;
                background-color: #2563eb;
                color: white;
                text-decoration: none;
                border-radius: 4px;
                font-weight: bold;
            }}
            .footer {{ margin-top: 20px; font-size: 12px; color: #6b7280; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Verify Your Email Address</h2>
            <p>Thank you for signing up with VerseCatch! To complete your registration, please verify your email address by clicking the button below:</p>
            
            <p><a href="{verification_url}" class="button">Verify Email Address</a></p>
            
            <p>If you didn't create an account with VerseCatch, you can safely ignore this email.</p>
            
            <div class="footer">
                <p>Best regards,<br>The VerseCatch Team</p>
                <p><small>This email was sent to {email}. If you believe you received this in error, please contact support.</small></p>
            </div>
        </div>
    </body>
    </html>
    """
    
    plain_text_content = f"""
    Verify Your VerseCatch Account
    ------------------------------
    
    Thank you for signing up with VerseCatch! To complete your registration, please verify your email address by visiting this link:
    
    {verification_url}
    
    If you didn't create an account with VerseCatch, you can safely ignore this email.
    
    Best regards,
    The VerseCatch Team
    """

    message = Mail(
        from_email=From(settings.EMAIL_FROM, "VerseCatch Team"),
        to_emails=To(email),
        subject=Subject("Verify Your VerseCatch Account"),
        html_content=HtmlContent(html_content),
        plain_text_content=plain_text_content
    )

    try:
        sg = sendgrid.SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
        response = sg.send(message)
        
        # Check for successful delivery
        if response.status_code not in [200, 202]:
            logger.error(f"Email send failed with status {response.status_code}")
            raise HTTPException(status_code=500, detail="Failed to send verification email")
            
        logger.info(f"Verification email sent to {email}")
        
    except Exception as e:
        logger.error(f"Error sending verification email: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send verification email")
    
def verify_paystack_signature(payload: bytes, signature: str) -> bool:
    secret = settings.PAYSTACK_SECRET_KEY
    computed_signature = hmac.new(
        secret.encode('utf-8'),
        msg=payload,
        digestmod=hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(computed_signature, signature)