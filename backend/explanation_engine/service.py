"""
OptiTrade Explanation Engine — facade.

Never predicts, never votes - `explain()` always takes an already-final
`DecisionOutput` and returns text describing it. Provider failures are
always caught here and replaced with a deterministic fallback; this
method is designed to never raise.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from decision_engine.models import DecisionOutput
from explanation_engine.config import ExplanationEngineConfig
from explanation_engine.exceptions import ExplanationProviderError
from explanation_engine.fallback import generate_fallback_explanation
from explanation_engine.groq_provider import GroqExplanationProvider
from explanation_engine.interfaces import ExplanationProviderProtocol
from explanation_engine.models import Explanation, ExplanationProvider

logger = logging.getLogger(__name__)


class ExplanationEngine:
    """Dependency-injectable facade. `provider` defaults to a lazily-
    constructed `GroqExplanationProvider` so merely constructing this
    engine (e.g. at app startup) never requires a configured
    `GROQ_API_KEY` until an explanation is actually requested."""

    def __init__(
        self,
        provider: Optional[ExplanationProviderProtocol] = None,
        config: Optional[ExplanationEngineConfig] = None,
    ) -> None:
        self.config = config or ExplanationEngineConfig.from_env()
        self._provider = provider

    @property
    def provider(self) -> ExplanationProviderProtocol:
        if self._provider is None:
            self._provider = GroqExplanationProvider(config=self.config)
        return self._provider

    def explain(self, decision: DecisionOutput, symbol: str) -> Explanation:
        try:
            text = self.provider.generate(decision, symbol)
        except Exception as exc:
            log_event(
                logger, component="explanation_engine", module="explanation_engine.service",
                operation="explain", status=STATUS_ERROR, symbol=symbol,
                error_type=type(exc).__name__, level=logging.WARNING,
            )
            return Explanation(
                text=generate_fallback_explanation(decision, symbol),
                provider=ExplanationProvider.FALLBACK, model="",
                generated_at=datetime.now(timezone.utc),
            )

        log_event(
            logger, component="explanation_engine", module="explanation_engine.service",
            operation="explain", status=STATUS_SUCCESS, symbol=symbol,
            provider=getattr(self.provider, "provider_name", "unknown"),
        )
        return Explanation(
            text=text, provider=ExplanationProvider.GROQ, model=self.config.model,
            generated_at=datetime.now(timezone.utc),
        )
