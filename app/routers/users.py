'''
    This file defines API endpoints for user operations such as create, read, delete
'''

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from datetime import datetime
import hashlib

from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserResponse, UserLogin

router = APIRouter(prefix="/users", tags=["users"])

def hash_password(password: str) -> str:
    """Hash password using SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()

@router.post("/login", response_model=UserResponse)
def login_user(login_data: UserLogin, db: Session = Depends(get_db)):
    """
    Login endpoint - validates user credentials
    Email can be either email address or username
    """
    print(f"🔍 Login attempt for: {login_data.email}")
    
    try:
        # Hash the provided password
        password_hash = hash_password(login_data.password)
        
        # Find user by email or username
        user = db.query(User).filter(
            ((User.email == login_data.email) | (User.username == login_data.email)) &
            (User.password_hash == password_hash)
        ).first()
        
        if not user:
            print(f"❌ Login failed: Invalid credentials")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email/username or password"
            )
        
        # Update last login time
        user.last_login = datetime.now()
        db.commit()
        
        print(f"✅ Login successful for user: {user.username}")
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Login error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login failed: {str(e)}"
        )

@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    """Create a new user"""
    print(f"🔍 Attempting to create user: {user.email}, {user.username}")
    
    try:
        # Check if user already exists
        existing_user = db.query(User).filter(
            (User.email == user.email) | (User.username == user.username)
        ).first()
        
        if existing_user:
            print(f"User already exists: email={existing_user.email}, username={existing_user.username}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email or username already exists"
            )
        
        # Create new user
        print(f"✅ Creating new user...")
        db_user = User(
            email=user.email,
            username=user.username,
            password_hash=hash_password(user.password)
        )
        
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
        print(f"✅ User created successfully: {db_user.user_id}")
        return db_user
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error creating user: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create user: {str(e)}"
        )

@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: UUID, db: Session = Depends(get_db)):
    """Get user by ID"""
    user = db.query(User).filter(User.user_id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: UUID, db: Session = Depends(get_db)):
    """Delete user by ID"""
    user = db.query(User).filter(User.user_id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    db.delete(user)
    db.commit()
    
    return None
