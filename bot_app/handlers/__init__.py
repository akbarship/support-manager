from aiogram import Router

from bot_app.handlers import admin, booking, common, support


def setup_routers() -> Router:
    router = Router()
    router.include_router(common.router)
    router.include_router(admin.router)
    router.include_router(booking.router)
    router.include_router(support.router)
    return router
