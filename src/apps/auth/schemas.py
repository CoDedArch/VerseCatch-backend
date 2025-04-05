from pydantic import BaseModel, Field, EmailStr, SecretStr
from typing import Optional
from datetime import datetime
from uuid import UUID

class Quote(BaseModel):
    """
    Pydantic model for a Bible quote.
    """
    version: str = Field(..., title="Bible version")
    book: str = Field(..., title="Book of the Bible")
    chapter: int = Field(..., title="Chapter number")
    verse_number: int = Field(..., title="Verse number")
    text: str = Field(..., title="Verse text")

    class Config:
        from_attributes = True


# User-related schemas
class UserBase(BaseModel):
    """
    Base schema for user operations.
    """
    email: EmailStr = Field(..., title="User email")


class UserCreate(UserBase):
    """
    Schema for creating a new user.
    """
    first_name: str = Field(..., title="First name", min_length=1, max_length=50)
    last_name: str = Field(..., title="Last name", min_length=1, max_length=50)
    password: SecretStr = Field(..., title="Password", min_length=8)
    bible_version: str = Field(..., title="Preferred Bible version")  # Add this field


class UserLogin(UserBase):
    """
    Schema for user login.
    """
    password: SecretStr = Field(..., title="Password")


class UserResponse(UserBase):
    """
    Schema for returning user information.
    """
    id: UUID
    first_name: str = Field(..., title="First name")
    last_name: str = Field(..., title="Last name")
    email: str = Field(..., title="User email")
    is_active: bool = Field(..., title="Is user active")
    verified: bool
    streak: int
    faith_coins: int
    current_tag: str
    bible_version: str = Field(..., title="Preferred Bible version")  # Add this field
    created_at: datetime = Field(..., title="User creation timestamp")
    has_taken_tour: bool = Field(..., title="Has the user taken the site tour") 

    class Config:
        from_attributes = True


class Token(BaseModel):
    """
    Schema for JWT token response.
    """
    access_token: str = Field(..., title="Access token")
    token_type: str = Field(default="bearer", title="Token type")


class TokenData(BaseModel):
    """
    Schema for data encoded in the JWT token.
    """
    email: Optional[str] = Field(None, title="User email")


# Request model for checking email
class EmailCheckRequest(BaseModel):
    email: str


# Response model for checking email
class EmailCheckResponse(BaseModel):
    exists: bool

class SignupResponse(BaseModel):
    message: str