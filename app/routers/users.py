'''
    This file defines API endpoints for user operations such as create, read, delete
'''

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
import hashlib


from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserResponse

#Creates a router for the related endpoints 
router = APIRouter(prefix="/users", tags=["users"])

# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# def hash_password(password: str) -> str:
#     # Uses Bcrypt to create a secure, salted hash
#     return pwd_context.hash(password)

# def verify_password(plain_password: str, hashed_password: str) -> bool:
#     # Safely checks the plain password against the stored hash
#     return pwd_context.verify(plain_password, hashed_password)
#     #return hashlib.sha256(password.encode()).hexdigest()

@router.post("/login", response_model=UserResponse)
def login_user(email: str, password: str, db: Session = Depends(get_db)):
    """
    Login endpoint - validates user credentials
    """
    # Hash the provided password
    password_hash = hash_password(password)
    
    # Find user by email or username
    user = db.query(User).filter(
        ((User.email == email) | (User.username == email)) &
        (User.password_hash == password_hash)
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email/username or password"
        )
    
    return user

#This is to create a new user
@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    #This checks if the user already exists or not
    existing_user = db.query(User).filter(
        (User.email == user.email) | (User.username == user.username)
    ).first()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email or username already exists"
        )
    
    #creates a new user
    db_user = User(
        email=user.email,
        username=user.username,
        password_hash=hash_password(user.password)
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return db_user

#This gets all the users 
@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: UUID, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user

#This deletes a user 
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: UUID, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    db.delete(user)
    db.commit()
    
    return None
