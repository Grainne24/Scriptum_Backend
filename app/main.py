'''
    This creates the FastAPI and registers all routers and sets up CORS
'''

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routers import users, books
from app.routers import stylometry  # Add this import

#Createa database tables
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

#This initialize FastAPI app
app = FastAPI(
    title="Scriptum API",
    description="Book recommendation API based on writing style",
    version="1.0.0"
)

#CORS middleware - this allows requests from any origin 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], #Right now its allowing all origins - need to be changed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#Health check endpoint
@app.get("/health", tags=["health"])
def health_check():
    return {
        "status": "healthy",
        "service": "Scriptum API",
        "version": "1.0.0"
    }

#Root endpoint
@app.get("/", tags=["root"])
def read_root():
    return {
        "message": "Welcome to Scriptum API",
        "docs": "/docs",
        "health": "/health"
    }

#This adds all endpoints from each router
app.include_router(users.router)
app.include_router(books.router)
app.include_router(stylometry.router)
