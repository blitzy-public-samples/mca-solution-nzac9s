from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.api import applications, merchants, attachments, webhooks
from app.core.config import get_settings
from app.core.security import get_current_user
from app.db.database import init_db
from app.core.logging import setup_logging

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    await init_db()
    setup_logging()

async def get_current_active_user(current_user = Depends(get_current_user)):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(applications.router, prefix="/api/applications", tags=["applications"])
app.include_router(merchants.router, prefix="/api/merchants", tags=["merchants"])
app.include_router(attachments.router, prefix="/api/attachments", tags=["attachments"])
app.include_router(webhooks.router, prefix="/api/webhooks", tags=["webhooks"])

# HUMAN ASSISTANCE NEEDED
# The following block might need additional configuration or error handling:
# - Verify if the CORS configuration is appropriate for the production environment
# - Consider adding rate limiting middleware
# - Implement proper error handling and logging middleware
# - Add health check endpoint
# - Configure Swagger UI and ReDoc