from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from jose import JWTError, jwt
from datetime import datetime
from core.database import aget_db
from apps.requotes.models import User
from apps.auth.schemas import UserCreate, UserResponse, Token, UserLogin, EmailCheckRequest, EmailCheckResponse
from apps.auth.utils import get_password_hash, verify_password, create_access_token, create_verification_token, send_verification_email, SECRET_KEY, ALGORITHM
from sqlalchemy import select



router = APIRouter()

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

@router.post("/auth/signup", response_model=Token)
async def signup(user: UserCreate, db: AsyncSession = Depends(aget_db)):
    """
    Register a new user and return a JWT token upon successful verification.
    """
    # Check if user already exists
    db_user = await db.execute(text("SELECT * FROM users WHERE email = :email"), {"email": user.email})
    db_user = db_user.scalar()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Hash the password
    hashed_password = get_password_hash(user.password.get_secret_value())

    
    # Create new user
    new_user = User(
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        password=hashed_password,
        verified=False,  # User is not verified yet
    )
    # Generate verification token
    verification_token = create_verification_token({"sub": new_user.email})

    # Send verification email
    await send_verification_email(new_user.email, verification_token)
    
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)


    # Generate JWT token for the user
    access_token = create_access_token(data={"sub": new_user.email})

    # Return the token and user details
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": new_user.id,
            "first_name": new_user.first_name,
            "last_name": new_user.last_name,
            "email": new_user.email,
            "is_active": new_user.is_active,
            "verified": new_user.verified,
            "created_at": datetime.utcnow(),  # Manually set created_at
        }
    }


#verify route
@router.get("/auth/verify")
async def verify_email(token: str, db: AsyncSession = Depends(aget_db)):
    print("recieved")
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

    # Find the user
    result = await db.execute(select(User).where(User.email == email))
    db_user = result.scalar_one_or_none()
    if db_user is None:
        raise credentials_exception

    # Mark the user as verified
    db_user.verified = True
    await db.commit()

    return {"message": "Email verified successfully"}


# Login Route
@router.post("/auth/login", response_model=Token)
async def login(user: UserLogin, db: AsyncSession = Depends(aget_db)):
    # Find user by email
    result = await db.execute(select(User).where(User.email == user.email))
    db_user = result.scalar_one_or_none()

    # Check if user exists and verify password
    if not db_user or not verify_password(user.password.get_secret_value(), db_user.password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")

    # Check if the user is verified
    if not db_user.verified:
        raise HTTPException(status_code=400, detail="Email not verified")

    # Generate JWT token
    access_token = create_access_token(data={"sub": db_user.email})
    return {"access_token": access_token, "token_type": "bearer"}


# Protected Route Example
@router.get("/me", response_model=UserResponse)
async def read_users_me(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(aget_db)):
    """
    Fetch the current authenticated user's details.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    db_user = await db.execute(text("SELECT * FROM users WHERE email = :email"), {"email": email})
    db_user = db_user.scalar()
    if db_user is None:
        raise credentials_exception
    return db_user


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