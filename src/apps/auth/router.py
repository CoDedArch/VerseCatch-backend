import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from core.database import aget_db
from apps.requotes.models import User, UserActivity,Achievement, UnverifiedUser, UserTheme, Theme, Payment
from apps.auth.schemas import UserCreate, LoginRequest, Token, EmailCheckRequest, EmailCheckResponse, SignupResponse
from apps.auth.utils import get_password_hash, verify_password, create_access_token, create_verification_token, send_verification_email, SECRET_KEY, ALGORITHM, verify_paystack_signature
from sqlalchemy import select, func, distinct, delete
from sqlalchemy.orm import selectinload
from fastapi import WebSocket, WebSocketDisconnect
from core.security import verify_api_key
import random
import json
import os
import hmac
import hashlib
import httpx


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
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
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
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
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
                await award_achievement(db, db_user, "Daily Devotee", "Daily Devotee", 7)
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
            "has_taken_tour": db_user.has_taken_tour,  # Include the new field
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
                    "has_taken_tour": db_user.has_taken_tour,  # Include the new field
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
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
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
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Get user
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # Get all themes
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
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    theme_id = data.get("theme_id")
    via_ad = data.get("via_ad", False)

    if not theme_id:
        raise HTTPException(status_code=400, detail="Theme ID is required")

    # Get user
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # Get theme
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
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        print(email)
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    theme_id = data.get("theme_id")
    if not theme_id:
        raise HTTPException(status_code=400, detail="Theme ID is required")

    # Get user
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


 # List of inspirational verses
inspirational_verses = [
    {"book": "Psalms", "chapter": 23, "verse": 1, "text": "The Lord is my shepherd; I shall not want."},
    {"book": "Proverbs", "chapter": 3, "verse": 5, "text": "Trust in the Lord with all your heart and lean not on your own understanding."},
    {"book": "Isaiah", "chapter": 40, "verse": 31, "text": "But they that wait upon the Lord shall renew their strength; they shall mount up with wings as eagles."},
    {"book": "Philippians", "chapter": 4, "verse": 13, "text": "I can do all things through Christ who strengthens me."},
    {"book": "Jeremiah", "chapter": 29, "verse": 11, "text": "For I know the plans I have for you, declares the Lord, plans to prosper you and not to harm you, plans to give you hope and a future."},
    {"book": "Romans", "chapter": 8, "verse": 28, "text": "And we know that in all things God works for the good of those who love him, who have been called according to his purpose."},
    {"book": "Matthew", "chapter": 11, "verse": 28, "text": "Come to me, all you who are weary and burdened, and I will give you rest."},
    {"book": "Joshua", "chapter": 1, "verse": 9, "text": "Have I not commanded you? Be strong and courageous. Do not be afraid; do not be discouraged, for the Lord your God will be with you wherever you go."},
    {"book": "2 Timothy", "chapter": 1, "verse": 7, "text": "For the Spirit God gave us does not make us timid, but gives us power, love and self-discipline."},
    {"book": "John", "chapter": 16, "verse": 33, "text": "I have told you these things, so that in me you may have peace. In this world you will have trouble. But take heart! I have overcome the world."},
    {"book": "Psalm", "chapter": 46, "verse": 1, "text": "God is our refuge and strength, an ever-present help in trouble."},
    {"book": "Isaiah", "chapter": 41, "verse": 10, "text": "So do not fear, for I am with you; do not be dismayed, for I am your God. I will strengthen you and help you; I will uphold you with my righteous right hand."},
    {"book": "Hebrews", "chapter": 11, "verse": 1, "text": "Now faith is confidence in what we hope for and assurance about what we do not see."},
    {"book": "1 Peter", "chapter": 5, "verse": 7, "text": "Cast all your anxiety on him because he cares for you."},
    {"book": "Deuteronomy", "chapter": 31, "verse": 6, "text": "Be strong and courageous. Do not be afraid or terrified because of them, for the Lord your God goes with you; he will never leave you nor forsake you."},
]


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
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
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
        cache_minutes = 5 if has_daily_devotee else 30

        try:
            print("Updating user with new verse")

            verse_json = json.dumps(selected_verse)
            try:
                json.loads(verse_json)  # Test roundtrip
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=500, detail="Invalid verse data format")

            user.last_inspirational_verse = json.dumps(selected_verse)
            user.next_inspirational_verse_time = current_time + timedelta(minutes=cache_minutes)
            db.add(user)
            try:
                await db.flush()  # Will raise any integrity errors
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
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Get user
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    amount = data.get("amount")
    if not amount or amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")

    # Generate unique reference
    reference = f"VC-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"

    # Create payment record
    # Fetch real exchange rate from an external API
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("https://api.exchangerate-api.com/v4/latest/GHS")
        exchange_data = response.json()
        usd_rate = exchange_data["rates"].get("USD", 12)  # Default to 12 if USD rate is not found
    except Exception as e:
        usd_rate = 12  # Fallback to default rate in case of an error

    new_payment = Payment(
        user_id=user.id,
        amount=amount,
        currency="GHS",
        paystack_reference=reference,
        status="pending",
        metadata={
            "donation_type": "supporter" if amount >= 5 else "standard",
            "original_usd_amount": amount / usd_rate  
        }
    )
    db.add(new_payment)
    await db.commit()

    # Initialize Paystack payment
    try:
        payload = {
            "email": email,
            "amount": int(amount * 100),  # Convert to pesewas
            "reference": reference,
            "currency": "GHS",
            "callback_url": f"{os.getenv('BASE_URL')}/payment/verify",
            "metadata": {
                "payment_id": str(new_payment.id),
                "user_id": str(user.id)
            }
        } 
        headers={
                "Authorization": f"Bearer {os.getenv('PAYSTACK_SECRET_KEY')}",
                "Content-Type": "application/json"
            }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.paystack.co/transaction/initialize",
                json=payload,
                headers=headers
            )
        data = response.json()
        if response.status_code != 200 or not data.get("status"):
            raise Exception(data.get("message", "Unknown error from Paystack"))
        return {
            "authorization_url": response.data["data"]["authorization_url"],
            "reference": reference
        }
    
    except Exception as e:
        new_payment.status = "failed"
        new_payment.metadata["error"] = str(e)
        await db.commit()
        raise HTTPException(status_code=500, detail="Payment initialization failed")
    
# Payment Verification Endpoint
@router.post("/api/verify-payment")
async def verify_payment(
    data: dict,
    db: AsyncSession = Depends(aget_db)
):
    reference = data.get("reference")
    if not reference:
        raise HTTPException(status_code=400, detail="Reference required")

    # Verify with Paystack
    try:
        url = f"https://api.paystack.co/transaction/verify/{reference}"
        headers = {
            "Authorization": f"Bearer {os.getenv('PAYSTACK_SECRET_KEY')}"
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)

        data = response.data["data"]
        
        # Update payment record
        result = await db.execute(
            select(Payment)
            .where(Payment.paystack_reference == reference)
        )
        payment = result.scalar_one_or_none()
        
        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")

        if data["status"] == "success":
            payment.status = "success"
            payment.payment_method = data["channel"]
            payment.completed_at = datetime.now()
            
            # Update user status if supporter donation
            if payment.amount >= 5:
                user = await db.get(User, payment.user_id)
                user.is_supporter = True
                db.add(user)
            
            await db.commit()
            return {"status": "success"}
        else:
            payment.status = "failed"
            await db.commit()
            return {"status": "failed"}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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