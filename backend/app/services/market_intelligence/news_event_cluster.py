"""Cluster related news events by headline similarity."""

from __future__ import annotations

from news_intelligence.news_deduplicator import normalize_headline
from news_intelligence.news_models import NewsItem


def _similarity(a: str, b: str) -> float:
    from difflib import SequenceMatcher
    return SequenceMatcher(None, normalize_headline(a), normalize_headline(b)).ratio()


class NewsEventCluster:
    def related_symbols(self, item: NewsItem, peers: list[NewsItem], threshold: float = 0.75) -> list[str]:
        related: set[str] = set(item.symbols or [])
        if item.symbol and item.symbol != "MARKET":
            related.add(item.symbol)
        nh = item.headline
        for peer in peers:
            if peer.id == item.id:
                continue
            if _similarity(nh, peer.headline) >= threshold:
                if peer.symbol and peer.symbol != "MARKET":
                    related.add(peer.symbol)
                related.update(peer.symbols or [])
        related.discard("MARKET")
        return sorted(related)

    def attach_related(self, items: list[NewsItem]) -> list[dict]:
        from app.services.news_intelligence_api_service import _importance, _item_to_event, _label_display

        out: list[dict] = []
        for item in items:
            ev = _item_to_event(item)
            ev["relatedSymbols"] = self.related_symbols(item, items)
            ev["importance"] = _importance(item)
            ev["sentiment"] = _label_display(item.sentiment_label)
            out.append(ev)
        return out
