"""
Normalizer stage — cleans raw text and computes a stable content hash
used by the Deduplicator.
"""
from __future__ import annotations

import hashlib
import re

from news.models import NewsItemContext, RawNewsItem


class NewsNormalizer:
    def normalize(self, raw: RawNewsItem) -> NewsItemContext:
        title   = self._clean(raw.title)
        summary = self._clean(raw.summary)
        text    = f"{title}. {summary}" if summary else title

        content_hash = hashlib.sha1(
            re.sub(r"[^a-z0-9]", "", title.lower()).encode("utf-8")
        ).hexdigest()

        return NewsItemContext(raw=raw, text=text, content_hash=content_hash)

    @staticmethod
    def _clean(value: str) -> str:
        value = re.sub(r"<[^>]+>", " ", value or "")
        return re.sub(r"\s+", " ", value).strip()
