#!/usr/bin/env python3
"""
OptiTrade — Canlı Terminal Dashboard (Bloomberg Terminali Tarzı)
====================================================================
GUI'siz Linux sunucularda ``HybridTradingEngine``'i periyodik olarak
(varsayılan 60 saniyede bir) tetikleyip sonuçları ``rich.live`` ile
canlı güncellenen, tam ekran bir terminal arayüzünde gösterir.

Motorun 15 dakikalık öneri cache'i sayesinde ardışık döngülerin çoğu
LLM'e (Groq) yeniden istek atmaz — sadece piyasa rejimi/fiyat taraması
her döngüde tazelenir.

Sol panel: taranan tüm sembollerin özet tablosu.
Sağ panel: rakam tuşlarıyla (1-9) seçilen sembolün tam AI yorumu ve
risk (SL/TP) seviyeleri.

Kullanım (backend/ dizininden):
    export GROQ_API_KEY="gsk_..."   # veya backend/.env dosyasına ekleyin
    python3 dashboard.py

Çıkmak için Ctrl+C.
"""
from __future__ import annotations

import logging
import os
import queue
import select
import sys
import threading
import time
from datetime import datetime
from typing import List, Optional

from dotenv import load_dotenv
from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

REFRESH_INTERVAL_SECONDS = 60
SYMBOLS: List[str] = ["BTC-USD", "AAPL", "THYAO.IS"]

console = Console()

_SIGNAL_TEXT_STYLE = {
    "STRONG_BUY": "bold white on green",
    "BUY": "bold green",
    "NEUTRAL": "bold yellow",
    "SELL": "bold red",
    "STRONG_SELL": "bold white on red",
}
_SIGNAL_ACCENT_STYLE = {
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
                '  [cyan]export GROQ_API_KEY="gsk_..."[/cyan]  veya backend/.env dosyasına ekleyin.',
                title="[bold red]Ortam Kontrolü Başarısız[/bold red]",
                border_style="red",
            )
        )
        sys.exit(1)


class _KeypressReader:
    """Terminali cbreak moduna alıp tek karakterlik tuş basımlarını arka
    planda ayrı bir thread üzerinden okuyan yardımcı sınıf.

    Ana döngü ``engine.run()`` çağrısı sırasında (birkaç saniye) bloklansa
    bile tuş basımları kaybolmaz — bir kuyrukta biriktirilir. Standart giriş
    bir terminale bağlı değilse (ör. bir pipe/cron içinde çalıştırılırsa)
    tuş okumayı sessizce devre dışı bırakır.
    """

    def __init__(self) -> None:
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._stop = threading.Event()
        self._original_settings = None
        self._thread: Optional[threading.Thread] = None

    def __enter__(self) -> "_KeypressReader":
        if not sys.stdin.isatty():
            return self
        import termios
        import tty

        self._original_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        return self

    def _read_loop(self) -> None:
        while not self._stop.is_set():
            ready, _, _ = select.select([sys.stdin], [], [], 0.2)
            if ready:
                self._queue.put(sys.stdin.read(1))

    def poll(self) -> Optional[str]:
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def __exit__(self, *exc_info) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        if self._original_settings is not None:
            import termios

            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._original_settings)


def _build_table(recommendations: List, selected_index: int) -> Table:
    table = Table(title="Piyasa Taraması", expand=True, show_lines=False)
    table.add_column("#", width=3, justify="center")
    table.add_column("Sembol", style="bold")
    table.add_column("Rejim")
    table.add_column("Sinyal")
    table.add_column("Güven", justify="right")
    table.add_column("Giriş", justify="right")

    for idx, rec in enumerate(recommendations):
        signal = rec.signal.value
        is_selected = idx == selected_index
        marker = f"➤{idx + 1}" if is_selected else f" {idx + 1}"
        table.add_row(
            marker,
            rec.symbol,
            rec.market_regime,
            Text(signal, style=_SIGNAL_TEXT_STYLE.get(signal, "white")),
            f"{rec.confidence_score}/100",
            f"{rec.entry_price:,.2f}",
            style="on grey15" if is_selected else None,
        )
    return table


def _build_detail_panel(rec) -> Panel:
    if rec is None:
        return Panel(
            Align.center("Veri bekleniyor...", vertical="middle"),
            title="AI Analizi",
            border_style="dim",
        )

    signal = rec.signal.value
    border = _SIGNAL_ACCENT_STYLE.get(signal, "white")

    body = Table.grid(padding=(0, 2))
    body.add_column(justify="right", style="dim")
    body.add_column()
    body.add_row("Piyasa Rejimi", rec.market_regime)
    body.add_row("Sinyal", Text(f" {signal} ", style=_SIGNAL_TEXT_STYLE.get(signal, "white")))
    body.add_row("AI Güven Skoru", f"{rec.confidence_score}/100")
    body.add_row("", "")
    body.add_row("Giriş Fiyatı", f"{rec.entry_price:,.4f}")
    body.add_row("Stop-Loss", Text(f"{rec.stop_loss:,.4f}", style="red"))
    body.add_row("Take-Profit 1", Text(f"{rec.take_profit_1:,.4f}", style="green"))
    body.add_row("Take-Profit 2", Text(f"{rec.take_profit_2:,.4f}", style="green"))
    body.add_row("", "")
    body.add_row("Yorum", Text(rec.trader_commentary, style="italic"))

    return Panel(
        body,
        title=f"[bold]{rec.symbol}[/bold] — AI Analizi",
        border_style=border,
        padding=(1, 2),
    )


def _build_layout(
    recommendations: List,
    selected_index: int,
    last_updated: Optional[datetime],
    next_refresh_in: int,
) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )
    layout["body"].split_row(Layout(name="left", ratio=3), Layout(name="right", ratio=2))

    layout["header"].update(
        Panel(
            Align.center(Text("OptiTrade — Hibrit Ticaret Motoru | Canlı Dashboard", style="bold cyan")),
            border_style="cyan",
        )
    )

    if recommendations:
        layout["left"].update(Panel(_build_table(recommendations, selected_index), border_style="blue"))
        selected = recommendations[selected_index] if 0 <= selected_index < len(recommendations) else None
        layout["right"].update(_build_detail_panel(selected))
    else:
        layout["left"].update(
            Panel(Align.center("Veri bekleniyor...", vertical="middle"), title="Piyasa Taraması", border_style="blue")
        )
        layout["right"].update(_build_detail_panel(None))

    ts = last_updated.strftime("%H:%M:%S") if last_updated else "—"
    footer_text = (
        f"Son güncelleme: [bold]{ts}[/bold]   |   Sonraki yenileme: [bold]{next_refresh_in}s[/bold]   |   "
        f"[dim]1-9: sembol seç · Ctrl+C: çıkış[/dim]"
    )
    layout["footer"].update(Panel(Align.center(Text.from_markup(footer_text)), border_style="dim"))

    return layout


def main() -> None:
    load_dotenv()
    _check_environment()
    # Tam ekran canlı arayüz, ham log satırlarıyla bölünmesin diye sadece
    # kritik hataları basıyoruz.
    logging.basicConfig(level=logging.ERROR)

    from core.hybrid_engine import HybridTradingEngine

    engine = HybridTradingEngine()

    recommendations: List = []
    selected_index = 0
    last_updated: Optional[datetime] = None
    last_run_at = 0.0

    with _KeypressReader() as keys, Live(
        _build_layout(recommendations, selected_index, last_updated, REFRESH_INTERVAL_SECONDS),
        console=console,
        screen=True,
        refresh_per_second=4,
    ) as live:
        try:
            while True:
                key = keys.poll()
                if key and key.isdigit():
                    idx = int(key) - 1
                    if 0 <= idx < len(recommendations):
                        selected_index = idx

                now = time.time()
                if last_updated is None or now - last_run_at >= REFRESH_INTERVAL_SECONDS:
                    fresh = engine.run(SYMBOLS)
                    if fresh:
                        recommendations = fresh
                        selected_index = min(selected_index, len(recommendations) - 1)
                    last_updated = datetime.now()
                    last_run_at = now

                next_refresh_in = max(0, int(REFRESH_INTERVAL_SECONDS - (time.time() - last_run_at)))
                live.update(_build_layout(recommendations, selected_index, last_updated, next_refresh_in))
                time.sleep(0.25)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
