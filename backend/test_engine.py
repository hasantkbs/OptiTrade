#!/usr/bin/env python3
"""
OptiTrade — Hybrid Trading Engine Terminal Test Script
=========================================================
GUI'siz (headless) Linux sunucularda terminalden çalıştırmak için:
HybridTradingEngine'i örnek sembollerle çağırır, sonuçları rich panelleri
olarak ekrana basar. Hiçbir grafik/plot penceresi açmaz.

Kullanım (backend/ dizininden):
    export GROQ_API_KEY="gsk_..."
    python3 test_engine.py

Alternatif olarak, her seferinde export etmemek için backend/.env dosyasına
tek satır ekleyebilirsiniz:
    GROQ_API_KEY=gsk_...
"""
from __future__ import annotations

import logging
import os
import sys
from typing import List

from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

SYMBOLS: List[str] = ["BTC-USD", "AAPL", "THYAO.IS"]

_SIGNAL_TEXT_STYLE = {
    "STRONG_BUY": "bold white on green",
    "BUY": "bold green",
    "NEUTRAL": "bold yellow",
    "SELL": "bold red",
    "STRONG_SELL": "bold white on red",
}
_SIGNAL_BORDER_STYLE = {
    "STRONG_BUY": "green",
    "BUY": "green",
    "NEUTRAL": "yellow",
    "SELL": "red",
    "STRONG_SELL": "red",
}


def _check_environment() -> None:
    """GROQ_API_KEY tanımlı değilse hata panelini basıp süreçten çıkar."""
    if not os.getenv("GROQ_API_KEY"):
        console.print(
            Panel(
                "[bold red]GROQ_API_KEY[/bold red] ortam değişkeni tanımlı değil.\n\n"
                "Ücretsiz bir anahtarı [cyan]https://console.groq.com/keys[/cyan] "
                "adresinden alıp çalıştırmadan önce ayarlayın:\n"
                '  [cyan]export GROQ_API_KEY="gsk_..."[/cyan]',
                title="[bold red]Ortam Kontrolü Başarısız[/bold red]",
                border_style="red",
            )
        )
        sys.exit(1)


def _configure_logging() -> None:
    """Terminal-odaklı, rich tabanlı log çıktısı (GUI/plot açmaz)."""
    logging.basicConfig(
        level=logging.WARNING,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, show_path=False, markup=True)],
    )


def _confidence_bar(score: int) -> Text:
    """0-100 arası güven skorunu renkli bir ilerleme çubuğu olarak biçimlendirir."""
    filled = max(0, min(10, round(score / 10)))
    bar = "█" * filled + "░" * (10 - filled)
    color = "green" if score >= 66 else "yellow" if score >= 33 else "red"
    return Text(f"{bar}  {score}/100", style=color)


def _render_recommendation(rec) -> Panel:
    """Tek bir TradeRecommendation'ı okunaklı bir rich Panel'e dönüştürür."""
    signal = rec.signal.value
    text_style = _SIGNAL_TEXT_STYLE.get(signal, "white")
    border_style = _SIGNAL_BORDER_STYLE.get(signal, "white")

    body = Table.grid(padding=(0, 2))
    body.add_column(justify="right", style="dim")
    body.add_column()

    body.add_row("Piyasa Rejimi", rec.market_regime)
    body.add_row("Sinyal", Text(f" {signal} ", style=text_style))
    body.add_row("AI Güven Skoru", _confidence_bar(rec.confidence_score))
    body.add_row("", "")
    body.add_row("Giriş Fiyatı", f"{rec.entry_price:,.4f}")
    body.add_row("Stop-Loss", Text(f"{rec.stop_loss:,.4f}", style="red"))
    body.add_row("Take-Profit 1", Text(f"{rec.take_profit_1:,.4f}", style="green"))
    body.add_row("Take-Profit 2", Text(f"{rec.take_profit_2:,.4f}", style="green"))
    body.add_row("", "")
    body.add_row("Yorum", Text(rec.trader_commentary, style="italic"))

    return Panel(
        body,
        title=f"[bold]{rec.symbol}[/bold]",
        border_style=border_style,
        padding=(1, 2),
    )


def main() -> None:
    load_dotenv()  # backend/.env varsa GROQ_API_KEY'i oradan yükler
    _check_environment()
    _configure_logging()

    console.rule("[bold cyan]OptiTrade — Hybrid Trading Engine (Terminal Test)[/bold cyan]")
    console.print(f"Analiz edilecek semboller: [bold]{', '.join(SYMBOLS)}[/bold]\n")

    from core.hybrid_engine import HybridTradingEngine

    engine = HybridTradingEngine()

    with console.status(
        "[bold cyan]Tarama, çoklu zaman dilimi analizi ve AI değerlendirmesi çalışıyor...[/bold cyan]",
        spinner="dots",
    ):
        recommendations = engine.run(SYMBOLS)

    console.print()

    if not recommendations:
        console.print(
            Panel(
                "Hiçbir sembol için öneri üretilemedi.\n"
                "Olası nedenler: piyasa rejimi filtresi tüm sembolleri eledi, "
                "veri çekilemedi veya AI çağrısı başarısız oldu.\n\n"
                "Detaylar için yukarıdaki log satırlarını kontrol edin.",
                title="[bold yellow]Sonuç Yok[/bold yellow]",
                border_style="yellow",
            )
        )
        return

    for rec in recommendations:
        console.print(_render_recommendation(rec))
        console.print()

    console.rule(f"[bold cyan]{len(recommendations)}/{len(SYMBOLS)} sembol için öneri üretildi[/bold cyan]")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Kullanıcı tarafından durduruldu.[/yellow]")
        sys.exit(130)
    except Exception:
        console.print_exception(show_locals=False)
        sys.exit(1)
