"""
OptiTrade — Paylaşılan Rate Limiter
======================================
``main.py`` ve ``api/`` altındaki ayrı router modülleri arasında circular
import olmadan aynı slowapi ``Limiter`` örneğini paylaşmak için. ``main.py``
kendi ``Limiter``'ını burada tanımlanana yönlendirir; yeni router'lar
(ör. ``api/v1/endpoints/signals.py``) doğrudan buradan import eder.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
