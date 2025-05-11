import asyncio
import random
import json
import httpx
from jose import JWTError, jwt
from core.config import settings
from core.database import aget_db
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta
from core.security import verify_api_key
from . constants import inspirational_verses
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import OAuth2PasswordBearer
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select, func, distinct, delete
from fastapi import APIRouter, Depends, HTTPException, status, Request
from apps.requotes.models import User, UserActivity,Achievement, UnverifiedUser, UserTheme, Theme, Payment, Rating
from apps.auth.schemas import UserCreate, LoginRequest, Token, EmailCheckRequest, EmailCheckResponse, SignupResponse
from apps.auth.utils import get_password_hash, verify_password, create_access_token, create_verification_token, send_verification_email, verify_paystack_signature

router = APIRouter()

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

async def cleanup_unverified_users(db: AsyncSession):
    """
    Delete unverified users older than 24 hours.
    """
    expiration_time = datetime.utcnow() - timedelta(hours=24)
    await db.execute(delete(UnverifiedUser).where(UnverifiedUser.created_at < expiration_time))
    await db.commit()

# update the state of whether a user has teken a tour of the site
@router.post("/api/update-has-taken-tour")
async def update_has_taken_tour(
    data: dict, 
    db: AsyncSession = Depends(aget_db)
):
    print("Updating has_taken_tour!")
    email = data.get("email")
    has_taken_tour = data.get("has_taken_tour")

    if not email or has_taken_tour is None:
        raise HTTPException(
            status_code=400, 
            detail="Email and has_taken_tour are required"
        )

    # Find the user by email
    result = await db.execute(select(User).where(User.email == email))
    db_user = result.scalar_one_or_none()

    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update the user's has_taken_tour field
    db_user.has_taken_tour = has_taken_tour
    await db.commit()

    return {"message": "has_taken_tour updated successfully"}


# update the user bible version preference
@router.post("/api/update-bible-version")
async def update_bible_version(data: dict, db: AsyncSession = Depends(aget_db)):
    email = data.get("email")
    bible_version = data.get("bible_version")

    if not email or not bible_version:
        raise HTTPException(status_code=400, detail="Email and Bible version are required")

    # Find the user by email
    result = await db.execute(select(User).where(User.email == email))
    db_user = result.scalar_one_or_none()

    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update the user's Bible version
    db_user.bible_version = bible_version
    await db.commit()

    return {"message": "Bible version updated successfully"}


@router.post("/auth/signup", response_model=SignupResponse)
async def signup(user: UserCreate, db: AsyncSession = Depends(aget_db)):
    """
    Register a new user and store them temporarily until email verification.
    """
    result = await db.execute(select(User).where(User.email == user.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = get_password_hash(user.password.get_secret_value())
    
    verification_token = create_verification_token({"sub": user.email})

    new_unverified_user = UnverifiedUser(
        user_name=user.user_name,
        email=user.email,
        password=hashed_password,
        bible_version=user.bible_version,
        verification_token=verification_token,
    )

    db.add(new_unverified_user)
    await db.commit()

    await send_verification_email(user.email, verification_token)

    return {"message": "Verification email sent. Please check your inbox."}


#verify route
@router.get("/auth/verify")
async def verify_email(token: str, db: AsyncSession = Depends(aget_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid verification token",
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(UnverifiedUser).where(UnverifiedUser.email == email))
    unverified_user = result.scalar_one_or_none()
    if unverified_user is None:
        raise credentials_exception

    new_user = User(
        user_name=unverified_user.user_name,
        email=unverified_user.email,
        password=unverified_user.password,
        verified=True,
        streak=0,
        faith_coins=0,
        current_tag="Newbie",
        bible_version=unverified_user.bible_version,
    )

    db.add(new_user)

    await db.delete(unverified_user)

    await db.commit()

    return {"message": "Email verified successfully"}


# login endpoint
@router.post("/auth/login", response_model=Token)
async def login(user: LoginRequest, db: AsyncSession = Depends(aget_db)):
    """
    Log in a user using either email or username and return a JWT token.
    """
    print("user requested:",user)
    # Find user by email or username
    result = await db.execute(
        select(User).where((User.email == user.identifier) | (User.user_name == user.identifier))
    )
    db_user = result.scalar_one_or_none()

    # Check if user exists and verify password
    if not db_user or not verify_password(user.password.get_secret_value(), db_user.password):
        print("User Not created")
        raise HTTPException(status_code=400, detail="Incorrect email/username or password")

    if not db_user.verified:
        raise HTTPException(status_code=400, detail="Email not verified")

    today = datetime.utcnow().date()
    last_login_date = db_user.last_login.date() if db_user.last_login else None

    if last_login_date != today:
        # Check if the user has any previous login activity
        result = await db.execute(
            select(UserActivity)
            .where(UserActivity.user_id == db_user.id, UserActivity.activity_type == "daily_login")
            .order_by(UserActivity.activity_date.desc())
        )
        previous_activity = result.scalars().first()

        if previous_activity:
            if previous_activity.activity_date.date() == (today - timedelta(days=1)):
                db_user.streak += 1
            else:
                db_user.streak = 1
        else:
            db_user.streak = 0

        db_user.last_login = datetime.utcnow()

        # Log the daily login activity
        new_activity = UserActivity(
            user_id=db_user.id,
            activity_type="daily_login",
            activity_date=datetime.utcnow(),
        )
        db.add(new_activity)
        await db.commit()

    access_token = create_access_token(data={"sub": db_user.email})

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.post("/auth/check-email", response_model=EmailCheckResponse)
async def check_email(request: EmailCheckRequest, db: AsyncSession = Depends(aget_db)):
    """
    Check if an email already exists in the database.
    """
    # Query the database to check if the email exists
    result = await db.execute(select(User).where(User.email == request.email))
    db_user = result.scalar_one_or_none()

    # Return whether the email exists
    return {"exists": db_user is not None}


async def award_achievement(session, user, name, tag, requirement):
    """Check if a user qualifies for an achievement and award it if not already given."""
    existing_achievement = await session.execute(
        select(Achievement).where(Achievement.user_id == user.id, Achievement.tag == tag)
    )
    if not existing_achievement.scalar_one_or_none():
        new_achievement = Achievement(user_id=user.id, name=name, tag=tag, requirement=requirement)
        session.add(new_achievement)
        await session.commit()


@router.websocket("/ws/auth/me")
async def websocket_user_details(websocket: WebSocket, db: AsyncSession = Depends(aget_db)):
    """
    WebSocket endpoint for real-time updates on user details, including achievements, total verses caught, and unique books caught.
    """
    api_key = websocket.query_params.get("api_key")

    if not verify_api_key(api_key):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    try:
        # Receive the JWT token from the client
        token = await websocket.receive_text()

        # Decode the token to get the user's email
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            email: str = payload.get("sub")
            if email is None:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
        except JWTError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # Find the user
        result = await db.execute(select(User).where(User.email == email))
        db_user = result.scalar_one_or_none()
        if db_user is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        achievements_result = await db.execute(
            select(Achievement).where(Achievement.user_id == db_user.id)
        )
        achievements = achievements_result.scalars().all()

        # Get user's payment status
        payments_result = await db.execute(
            select(Payment)
            .where(Payment.user_id == db_user.id)
            .order_by(Payment.completed_at.desc())
        )
        payments = payments_result.scalars().all()

        # Determine payment status
        has_paid = len(payments) > 0
        last_payment = payments[0] if has_paid else None
        payment_status = {
            "has_paid": has_paid,
            "last_payment_date": last_payment.created_at.isoformat() if last_payment else None,
            "last_payment_amount": float(last_payment.amount) if last_payment else None,
            "last_payment_currency": last_payment.currency if last_payment else None,
            "is_supporter": db_user.is_supporter,
            "total_payments": len(payments),
            "total_donated": float(sum(p.amount for p in payments)) if payments else 0
        }

        # Sort achievements by achieved_at to get the most recent one
        if achievements:
            most_recent_achievement = max(achievements, key=lambda a: a.achieved_at)
            db_user.current_tag = most_recent_achievement.tag
            await db.commit()

        total_verses_caught = await db.scalar(
            select(func.count()).where(
                UserActivity.user_id == db_user.id,
                UserActivity.activity_type == "verse_caught"
            )
        )

        unique_books_caught = await db.scalar(
            select(func.count(distinct(UserActivity.activity_data))).where(
                UserActivity.user_id == db_user.id,
                UserActivity.activity_type == "verse_caught"
            )
        )

        # Check if the user has logged in today
        today = datetime.utcnow().date()
        logged_in_today = db_user.last_login and db_user.last_login.date() == today

        # Update the last login time if the user hasn't logged in today
        if not logged_in_today:
            db_user.last_login = datetime.utcnow()
            db_user.streak += 1
            if db_user.streak >= 7:
                db_user.current_tag = "Daily Devotee"
                await award_achievement(db, db_user, "Daily Devotee", "Daily Devotee", "Login for 7 Conservative days")
            await db.commit()

        # Send initial user details
        await websocket.send_json({
            "id": str(db_user.id),
            "user_name": db_user.user_name,
            "email": db_user.email,
            "is_active": db_user.is_active,
            "verified": db_user.verified,
            "streak": db_user.streak,
            "faith_coins": db_user.faith_coins,
            "current_tag": db_user.current_tag,
            "bible_version": db_user.bible_version,
            "created_at": db_user.created_at.isoformat(),
            "logged_in_today": logged_in_today,
            "total_verses_caught": total_verses_caught,
            "unique_books_caught": unique_books_caught,
            "has_taken_tour": db_user.has_taken_tour,
            "payment_status": payment_status,
            "has_rated": db_user.has_rated,
            "achievements": [
                {
                    "id": str(achievement.id),
                    "name": achievement.name,
                    "tag": achievement.tag,
                    "requirement": achievement.requirement,
                    "achieved_at": achievement.achieved_at.isoformat(),
                }
                for achievement in achievements
            ],
        })

        # Keep the connection open and send updates
        try:
            while True:
                await asyncio.sleep(5)  # Adjust the interval as needed

                # Fetch the latest user data
                result = await db.execute(select(User).where(User.email == email))
                db_user = result.scalar_one_or_none()
                if db_user is None:
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return
                await db.refresh(db_user)

                achievements_result = await db.execute(
                    select(Achievement).where(Achievement.user_id == db_user.id)
                )
                achievements = achievements_result.scalars().all()
                # Get user's payment status
                payments_result = await db.execute(
                    select(Payment)
                    .where(Payment.user_id == db_user.id)
                    .order_by(Payment.completed_at.desc())
                )
                payments = payments_result.scalars().all()

                # Determine payment status
                has_paid = len(payments) > 0
                last_payment = payments[0] if has_paid else None
                payment_status = {
                    "has_paid": has_paid,
                    "last_payment_date": last_payment.created_at.isoformat() if last_payment else None,
                    "last_payment_amount": float(last_payment.amount) if last_payment else None,
                    "last_payment_currency": last_payment.currency if last_payment else None,
                    "is_supporter": db_user.is_supporter,
                    "total_payments": len(payments),
                    "total_donated": float(sum(p.amount for p in payments)) if payments else 0
                }

                # Sort achievements by achieved_at to get the most recent one
                if achievements:
                    most_recent_achievement = max(achievements, key=lambda a: a.achieved_at)
                    db_user.current_tag = most_recent_achievement.tag
                    await db.commit()

                total_verses_caught = await db.scalar(
                    select(func.count()).where(
                        UserActivity.user_id == db_user.id,
                        UserActivity.activity_type == "verse_caught"
                    )
                )

                unique_books_caught = await db.scalar(
                    select(func.count(distinct(UserActivity.activity_data))).where(
                        UserActivity.user_id == db_user.id,
                        UserActivity.activity_type == "verse_caught"
                    )
                )

                # Check if the user has logged in today
                logged_in_today = db_user.last_login and db_user.last_login.date() == today

                await websocket.send_json({
                    "id": str(db_user.id),
                    "user_name": db_user.user_name,
                    "email": db_user.email,
                    "is_active": db_user.is_active,
                    "verified": db_user.verified,
                    "streak": db_user.streak,
                    "faith_coins": db_user.faith_coins,
                    "current_tag": db_user.current_tag,
                    "bible_version": db_user.bible_version,
                    "created_at": db_user.created_at.isoformat(),
                    "logged_in_today": logged_in_today,
                    "total_verses_caught": total_verses_caught,
                    "unique_books_caught": unique_books_caught,
                    "has_taken_tour": db_user.has_taken_tour,
                    "payment_status": payment_status,
                    "has_rated": db_user.has_rated,
                    "achievements": [
                        {
                            "id": str(achievement.id),
                            "name": achievement.name,
                            "tag": achievement.tag,
                            "requirement": achievement.requirement,
                            "achieved_at": achievement.achieved_at.isoformat(),
                        }
                        for achievement in achievements
                    ],
                })

        except Exception as e:
            print(f"Error in while loop: {e}")
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)


@router.post("/auth/change-password")
async def change_password(
    data: dict,
    db: AsyncSession = Depends(aget_db),
    token: str = Depends(oauth2_scheme)
):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    current_password = data.get("current_password")
    new_password = data.get("new_password")

    if not current_password or not new_password:
        raise HTTPException(status_code=400, detail="Current and new password are required")

    # Find user by email
    result = await db.execute(select(User).where(User.email == email))
    db_user = result.scalar_one_or_none()

    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify current password
    if not verify_password(current_password, db_user.password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    # Update password
    db_user.password = get_password_hash(new_password)
    await db.commit()

    return {"message": "Password updated successfully"}


@router.get("/api/themes")
async def get_themes(
    db: AsyncSession = Depends(aget_db),
    token: str = Depends(oauth2_scheme)
):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    themes_result = await db.execute(select(Theme))
    themes = themes_result.scalars().all()

    # Get user's unlocked themes
    user_themes_result = await db.execute(
        select(UserTheme)
        .where(UserTheme.user_id == user.id)
    )
    user_themes = {ut.theme_id: ut for ut in user_themes_result.scalars()}

    response = []
    for theme in themes:
        user_theme = user_themes.get(theme.id)
        response.append({
            "id": str(theme.id),
            "name": theme.name,
            "display_name": theme.display_name,
            "price": theme.price,
            "styles": theme.styles,
            "preview_image_url": theme.preview_image_url,
            "unlocked": user_theme.unlocked if user_theme else False,
            "is_current": str(user.current_theme_id) == str(theme.id),
            "unlocked_via_ad": user_theme.unlocked_via_ad if user_theme else False
        })

    return response


@router.post("/api/unlock-theme")
async def unlock_theme(
    data: dict,
    db: AsyncSession = Depends(aget_db),
    token: str = Depends(oauth2_scheme)
):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    theme_id = data.get("theme_id")
    via_ad = data.get("via_ad", False)

    if not theme_id:
        raise HTTPException(status_code=400, detail="Theme ID is required")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    result = await db.execute(select(Theme).where(Theme.id == theme_id))
    theme = result.scalar_one_or_none()

    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")

    # Check if already unlocked
    result = await db.execute(
        select(UserTheme)
        .where(UserTheme.user_id == user.id)
        .where(UserTheme.theme_id == theme.id)
    )
    user_theme = result.scalar_one_or_none()

    if user_theme and user_theme.unlocked:
        return {"message": "Theme already unlocked"}

    # Handle via ad unlock
    if via_ad:
        # Here you would integrate with your ad service
        # For now we'll just mark it as unlocked via ad
        new_user_theme = UserTheme(
            user_id=user.id,
            theme_id=theme.id,
            unlocked=True,
            unlocked_at=datetime.utcnow(),
            unlocked_via_ad=True
        )
        db.add(new_user_theme)
        await db.commit()
        return {"message": "Theme unlocked via ad"}

    # Handle faith coin purchase
    if user.faith_coins < theme.price:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough faith coins. You need {theme.price} but have {user.faith_coins}"
        )

    user.faith_coins -= theme.price
    new_user_theme = UserTheme(
        user_id=user.id,
        theme_id=theme.id,
        unlocked=True,
        unlocked_at=datetime.utcnow(),
        unlocked_via_ad=False
    )
    db.add(new_user_theme)
    await db.commit()

    return {"message": "Theme unlocked successfully"}


@router.post("/api/set-theme")
async def set_theme(
    data: dict,
    db: AsyncSession = Depends(aget_db),
    token: str = Depends(oauth2_scheme)
):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        print(email)
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    theme_id = data.get("theme_id")
    if not theme_id:
        raise HTTPException(status_code=400, detail="Theme ID is required")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # Verify user has unlocked this theme
    result = await db.execute(
        select(UserTheme)
        .where(UserTheme.user_id == user.id)
        .where(UserTheme.theme_id == theme_id)
        .where(UserTheme.unlocked == True)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="You must unlock this theme first")

    # Set as current theme
    user.current_theme_id = theme_id
    await db.commit()

    return {"message": "Theme set as default successfully"}


# Endpoint to Recieve Inspirational-Verses
@router.get("/api/inspirational-verses")
async def get_inspirational_verses(
    db: AsyncSession = Depends(aget_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Retrieve inspirational verses from the Bible with their chapters and verses.
    The same verse will be returned until the next refresh time (5 minutes for Daily Devotee, 30 minutes otherwise).
    """
    try:
        # Authentication
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            if (email := payload.get("sub")) is None:
                raise HTTPException(status_code=401, detail="Invalid token credentials")
        except JWTError as e:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")

        # Fetch user with achievements
        try:
            result = await db.execute(
                select(User)
                .options(selectinload(User.achievements))
                .where(User.email == email)
            )
            user = result.scalar_one_or_none()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
        except Exception as e:
            raise HTTPException(status_code=500, detail="Error fetching user data")

        current_time = datetime.utcnow()
        
        # Check if we have a valid cached verse
        if user.last_inspirational_verse and user.next_inspirational_verse_time:
            print("user already has an inspirational verse")
            if current_time < user.next_inspirational_verse_time:
                try:
                    return {
                        "verse": json.loads(user.last_inspirational_verse),
                        "remaining_time": (user.next_inspirational_verse_time - current_time).total_seconds()
                    }
                except json.JSONDecodeError:
                    # Fall through to generate new verse if stored verse is invalid
                    pass

        # Validate inspirational verses exist
        if not inspirational_verses:
            raise HTTPException(status_code=500, detail="No inspirational verses available")

        print("user doesn't have an inspirational verse")

        # Select and store new verse
        selected_verse = random.choice(inspirational_verses)
        print("Selected verse:", selected_verse)
        has_daily_devotee = any(
            achievement.tag == "Daily Devotee" 
            for achievement in user.achievements
        )
        has_supporter = any(
            achievement.tag == "Supporter" 
            for achievement in user.achievements
        )

        # Determine cache time (priority: Supporter > Daily Devotee > Default)
        if has_supporter:
            cache_minutes = 5
        elif has_daily_devotee:
            cache_minutes = 15
        else:
            cache_minutes = 30

        try:
            print("Updating user with new verse")

            verse_json = json.dumps(selected_verse)
            try:
                json.loads(verse_json)
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=500, detail="Invalid verse data format")

            user.last_inspirational_verse = json.dumps(selected_verse)
            user.next_inspirational_verse_time = current_time + timedelta(minutes=cache_minutes)
            db.add(user)
            try:
                await db.flush()
                await db.commit()
                print("User updated successfully")
        
                return {
                    "verse": selected_verse,
                    "remaining_time": cache_minutes * 60
                }
            except Exception as e:
                await db.rollback()
                print(f"Error during commit: {str(e)}")  # Add this line
                raise HTTPException(status_code=500, detail="Failed to update user verse")
        except HTTPException:
            raise
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal server error")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
    

# Payment PayStack Endpoint
@router.post("/api/create-payment")
async def create_payment(
    data: dict,
    db: AsyncSession = Depends(aget_db),
    token: str = Depends(oauth2_scheme)
):
    print("Payment Request Recieved")
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    amount = data["amount"]
    if not amount or amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")

    # Generate unique reference
    try:
        reference = f"VC-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"

        new_payment = Payment(
            user_id=user.id,
            amount=amount,
            currency="GHS",
            paystack_reference=reference,
            status="pending",
            payment_metadata={
                "donation_type": "supporter" if data.get("metadata", {}).get("originalUsdAmount", 0) >= 5 else "standard",
                "original_usd_amount": data.get("metadata", {}).get("originalUsdAmount", 0)
            }
        )
        db.add(new_payment)
        await db.commit()
        print(f"Created payment with reference: {reference}")
        return {
                "reference": reference,
                "status": "pending",
                "payment_id": str(new_payment.id)
        }
    except Exception as e:
        print(f"Payment creation failed: {str(e)}") 
        raise HTTPException(status_code=500, detail=str(e))
    # # Initialize Paystack payment
    # try:
    #     payload = {
    #         "email": email,
    #         "amount": int(amount * 100),  # Convert to pesewas
    #         "reference": reference,
    #         "currency": "GHS",
    #         "callback_url": f"{os.getenv('BASE_URL')}/payment/verify",
    #         "metadata": {
    #             "payment_id": str(new_payment.id),
    #             "user_id": str(user.id)
    #         }
    #     } 
    #     headers={
    #             "Authorization": f"Bearer {os.getenv('PAYSTACK_SECRET_KEY')}",
    #             "Content-Type": "application/json"
    #         }
        
    #     async with httpx.AsyncClient() as client:
    #         response = await client.post(
    #             "https://api.paystack.co/transaction/initialize",
    #             json=payload,
    #             headers=headers
    #         )
    #     data = response.json()
    #     if response.status_code != 200 or not data.get("status"):
    #         raise Exception(data.get("message", "Unknown error from Paystack"))
    #     return {
    #         "authorization_url": response.data["data"]["authorization_url"],
    #         "reference": reference
    #     }
    
    # except Exception as e:
    #     new_payment.status = "failed"
    #     new_payment.metadata["error"] = str(e)
    #     await db.commit()
    #     raise HTTPException(status_code=500, detail="Payment initialization failed")
    
# Payment Verification Endpoint
@router.post("/api/verify-payment")
async def verify_payment(
    data: dict,
    db: AsyncSession = Depends(aget_db),
    token: str = Depends(oauth2_scheme)
):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")

        user_result = await db.execute(select(User).where(User.email == email))
        user = user_result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        reference = data.get("reference")
        if not reference:
            raise HTTPException(status_code=400, detail="Reference required")

        print(f"Verifying payment with reference: {reference}")

        # Check if payment exists in our database
        result = await db.execute(
            select(Payment)
            .where(Payment.paystack_reference == reference)
        )
        payment = result.scalar_one_or_none()

        if not payment:
            print(f"No local payment found for reference: {reference}")
            # Verify with Paystack
            try:

                url = f"https://api.paystack.co/transaction/verify/{reference}"
                headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}

                async with httpx.AsyncClient() as client:
                    paystack_response = await client.get(url, headers=headers)
                    paystack_data = paystack_response.json()

                if paystack_response.status_code != 200 or not paystack_data.get("status"):
                    raise HTTPException(
                        status_code=404,
                        detail="Payment not found in Paystack"
                    )

                # Create payment record from Paystack data
                paystack_amount = paystack_data["data"]["amount"] / 100  # Convert from pesewas
                metadata = {
                    "donation_type": "standard",
                    "original_usd_amount": 0  # Will be updated if we can calculate
                }

                # Try to get original USD amount if possible
                if "metadata" in paystack_data["data"]:
                    metadata["original_usd_amount"] = paystack_data["data"]["metadata"].get(
                        "originalUsdAmount", 0
                    )

                payment = Payment(
                    user_id=user.id,
                    amount=paystack_amount,
                    currency=paystack_data["data"]["currency"],
                    paystack_reference=reference,
                    status="pending",
                    payment_metadata=metadata
                )
                db.add(payment)
                await db.commit()
                await db.refresh(payment)
                print(f"Created new payment record from Paystack: {payment.id}")

            except Exception as e:
                print(f"Paystack verification failed: {str(e)}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Could not verify payment with Paystack: {str(e)}"
                )

        # Final verification with Paystack
        url = f"https://api.paystack.co/transaction/verify/{reference}"
        headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response_data = response.json()

        if response.status_code != 200 or not response_data.get("status"):
            print(f"Paystack verification failed: {response_data}")
            raise HTTPException(
                status_code=400,
                detail=response_data.get("message", "Payment verification failed")
            )

        transaction_data = response_data["data"]
        
        # Update payment record
        payment.status = transaction_data["status"]
        payment.payment_method = transaction_data.get("channel")
        payment.completed_at = datetime.now()
        
        # Update metadata if needed
        if "metadata" in transaction_data:
            payment.payment_metadata.update(transaction_data["metadata"])

        # Handle supporter status
        original_usd_amount = payment.payment_metadata.get("original_usd_amount", 0)
        is_supporter = original_usd_amount >= 5

        if is_supporter and user:
            await award_achievement(
                db, 
                user, 
                "VerseCatch Supporter", 
                "Supporter", 
                "Donated at least 5 USD equivalent"
            )
            user.is_supporter = True
            db.add(user)

        await db.commit()

        return {
            "status": "success",
            "isSupporter": is_supporter,
            "payment_id": str(payment.id),
            "amount": payment.amount,
            "currency": payment.currency
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Payment verification error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while verifying payment"
        )


# Verify PayStack Signature
@router.post("/api/payment-webhook")
async def payment_webhook(
    request: Request,
    db: AsyncSession = Depends(aget_db)
):
    # Verify Paystack signature
    payload = await request.body()
    signature = request.headers.get("x-paystack-signature")
    
    if not verify_paystack_signature(payload, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    event = await request.json()
    
    if event["event"] == "charge.success":
        reference = event["data"]["reference"]
        
        # Update payment record
        result = await db.execute(
            select(Payment)
            .where(Payment.paystack_reference == reference)
        )
        payment = result.scalar_one_or_none()
        
        if payment and payment.status == "pending":
            payment.status = "success"
            payment.payment_method = event["data"]["channel"]
            payment.completed_at = datetime.now()
            
            # Update user status if supporter donation
            if payment.amount >= 5:
                user = await db.get(User, payment.user_id)
                user.is_supporter = True
                db.add(user)
            
            await db.commit()

    return {"status": "success"}


# Rating Endpoint
@router.post("/api/submit-rating")
async def submit_rating(
    data: dict,
    db: AsyncSession = Depends(aget_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Submit a user rating for the app. Feedback is automatically generated based on the rating.
    
    Parameters:
    - rating: int (required, 1-5)
    
    Returns:
    - message: str
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    rating = data.get("rating")
    
    if rating is None:
        raise HTTPException(status_code=400, detail="Rating is required")
    
    try:
        rating = int(rating)
        if rating < 1 or rating > 5:
            raise ValueError("Rating must be between 1 and 5")
    except ValueError:
        raise HTTPException(status_code=400, detail="Rating must be an integer between 1 and 5")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.has_rated:
        raise HTTPException(status_code=400, detail="You have already submitted a rating")

    # Define rating descriptions
    rating_descriptions = {
        1: "Worse - Needs work",
        2: "Good - Has potential",
        3: "Better - Good but could improve",
        4: "Best - Really enjoying it",
        5: "Excellent - Perfect experience!"
    }

    # Get the automatic feedback based on rating
    feedback = rating_descriptions.get(rating, "")

    try:
        new_rating = Rating(
            user_id=user.id,
            rating=rating,
            feedback=feedback,
            created_at=datetime.utcnow()
        )
        db.add(new_rating)

        # Update user's rating fields
        user.rating = rating
        user.rating_feedback = feedback
        user.has_rated = True
        user.rated_at = datetime.utcnow()

        await db.commit()

        return {"message": "Thank you for your rating!"}

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to submit rating")


@router.get("/admin/user-ratings")
async def get_user_ratings(
    db: AsyncSession = Depends(aget_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Get all users with their ratings and feedback for admin dashboard
    """
    
    result = await db.execute(
        select(User)
        .options(selectinload(User.ratings))
        .where(User.has_rated == True)
        .order_by(User.rated_at.desc())
    )
    users = result.scalars().all()
    
    ratings_data = []
    for user in users:
        ratings_data.append({
            "id": str(user.id),
            "user_name": user.user_name,
            "email": user.email,
            "rating": user.rating,
            "rating_description": user.rating_description,
            "feedback": user.rating_feedback,
            "rated_at": user.rated_at.isoformat() if user.rated_at else None,
            "is_supporter": user.is_supporter,
            "total_verses_caught": await db.scalar(
                select(func.count()).where(
                    UserActivity.user_id == user.id,
                    UserActivity.activity_type == "verse_caught"
                )
            )
        })
    
    return {"users": ratings_data}


@router.get("/admin/user-stats")
async def get_user_stats(
    db: AsyncSession = Depends(aget_db),
    token: str = Depends(oauth2_scheme)
):
    """
    Get all users statistics including total count and ratings
    """
    
    total_users = await db.scalar(select(func.count(User.id)))
    
    users_with_ratings = await db.scalar(
        select(func.count(User.id))
        .where(User.has_rated == True)
    )
    
    return {
        "total_users": total_users,
        "users_with_ratings": users_with_ratings,
        "rating_percentage": round((users_with_ratings / total_users) * 100, 2) if total_users else 0
    }