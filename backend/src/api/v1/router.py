"""
OptiTrade — API v1 Router Aggregator
=======================================
``api/v1/endpoints/`` altındaki tüm endpoint modüllerini tek bir router
altında toplar; ``main.py``'a tek satırla (``app.include_router(api_v1_router)``)
bağlanır.

Yeni bir v1 endpoint modülü eklerken: ``api/v1/endpoints/<isim>.py`` içinde
bir ``router = APIRouter(prefix="/<isim>", ...)`` tanımlayıp aşağıya
``api_v1_router.include_router(<isim>.router)`` satırını ekleyin.
"""
from fastapi import APIRouter

from api.v1.endpoints import signals

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(signals.router)
