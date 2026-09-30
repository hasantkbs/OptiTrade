"""
OptiTrade — Dynamic Risk Manager (ATR Tabanlı Risk Katmanı)
==============================================================
Günlük ATR (Average True Range) değerine göre dinamik Stop-Loss ve
Take-Profit seviyeleri hesaplar, Risk/Ödül oranının minimum eşiği
karşılayıp karşılamadığını doğrular.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class RiskLevels(BaseModel):
    """ATR tabanlı hesaplanmış risk seviyeleri ve geçerlilik durumu."""

    entry_price: float
    atr: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_per_unit: float = Field(..., description="Entry - Stop Loss farkı")
    reward_per_unit_tp1: float = Field(..., description="TP1 - Entry farkı")
    risk_reward_ratio: float = Field(..., description="TP1 bazlı Risk/Ödül oranı")
    is_valid: bool = Field(..., description="Minimum Risk/Ödül eşiğini karşılıyor mu")


class DynamicRiskManager:
    """ATR'ye göre esnek Stop-Loss / Take-Profit seviyeleri üreten risk katmanı.

    Formüller (varsayılan çarpanlarla):
    - Stop-Loss: ``Entry - 1.5 * ATR``
    - Take-Profit 1: ``Entry + 2 * ATR``
    - Take-Profit 2: ``Entry + 3 * ATR``

    ``is_valid``, TP1 bazlı Risk/Ödül oranının ``min_risk_reward_ratio``
    (varsayılan 1:2) eşiğini karşılayıp karşılamadığını belirtir.
    """

    def __init__(
        self,
        stop_loss_atr_multiplier: float = 1.5,
        take_profit_1_atr_multiplier: float = 2.0,
        take_profit_2_atr_multiplier: float = 3.0,
        min_risk_reward_ratio: float = 2.0,
    ) -> None:
        self.stop_loss_atr_multiplier = stop_loss_atr_multiplier
        self.take_profit_1_atr_multiplier = take_profit_1_atr_multiplier
        self.take_profit_2_atr_multiplier = take_profit_2_atr_multiplier
        self.min_risk_reward_ratio = min_risk_reward_ratio

    def calculate(self, entry_price: float, atr: float) -> RiskLevels:
        """Verilen giriş fiyatı ve ATR için tam risk seviyeleri setini hesaplar."""
        if entry_price <= 0 or atr <= 0:
            raise ValueError("entry_price ve atr pozitif olmalı")

        stop_loss = entry_price - self.stop_loss_atr_multiplier * atr
        take_profit_1 = entry_price + self.take_profit_1_atr_multiplier * atr
        take_profit_2 = entry_price + self.take_profit_2_atr_multiplier * atr

        risk_per_unit = entry_price - stop_loss
        reward_per_unit_tp1 = take_profit_1 - entry_price
        risk_reward_ratio = reward_per_unit_tp1 / risk_per_unit if risk_per_unit > 0 else 0.0

        return RiskLevels(
            entry_price=round(entry_price, 4),
            atr=round(atr, 4),
            stop_loss=round(stop_loss, 4),
            take_profit_1=round(take_profit_1, 4),
            take_profit_2=round(take_profit_2, 4),
            risk_per_unit=round(risk_per_unit, 4),
            reward_per_unit_tp1=round(reward_per_unit_tp1, 4),
            risk_reward_ratio=round(risk_reward_ratio, 2),
            is_valid=risk_reward_ratio >= self.min_risk_reward_ratio,
        )
