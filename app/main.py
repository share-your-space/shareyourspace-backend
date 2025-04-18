from fastapi import FastAPI

def create_app() -> FastAPI:
    app = FastAPI(title="ShareYourSpace Backend")

    @app.get("/")
    async def root():
        return {"message": "Welcome to ShareYourSpace API"}

    # Include routers here later
    # from .routers import auth, users, etc.
    # app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    # app.include_router(users.router, prefix="/api/users", tags=["users"])

    return app

app = create_app() 