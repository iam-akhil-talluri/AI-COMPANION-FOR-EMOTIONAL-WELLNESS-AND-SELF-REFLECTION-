from typing import Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError

from app.errors import FRIENDLY_ERROR
from app.services.user_service import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, USERNAME_PATTERN

USERNAME_RULE = ("Usernames are 3-32 characters: letters, numbers, dots, dashes or underscores, "
                 "starting with a letter or number.")
PASSWORD_RULE = f"Your password must be {MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} characters."


class RegisterRequest(BaseModel):
    # Validated below to return user-friendly messages.
    username: str = Field(description="3-32 letters, digits, '.', '_' or '-'. "
                          "Choose a name that does not identify you.",
                          json_schema_extra={"pattern": USERNAME_PATTERN.pattern})
    password: str = Field(json_schema_extra={"minLength": MIN_PASSWORD_LENGTH, "maxLength": MAX_PASSWORD_LENGTH})

    @field_validator("username")
    @classmethod
    def _check_username(cls, value: str) -> str:
        if not USERNAME_PATTERN.match(value):
            raise PydanticCustomError(FRIENDLY_ERROR, USERNAME_RULE)
        return value

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        if not MIN_PASSWORD_LENGTH <= len(value) <= MAX_PASSWORD_LENGTH:
            raise PydanticCustomError(FRIENDLY_ERROR, PASSWORD_RULE)
        return value


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
    # Require the admin role; other accounts receive 403.
    admin: bool = False


class UserOut(BaseModel):
    username: str
    role: Literal["user", "admin"]


class AuthResponse(BaseModel):
    token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int
    user: UserOut
