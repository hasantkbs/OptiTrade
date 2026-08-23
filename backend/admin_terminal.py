#!/usr/bin/env python3
"""
OptiTrade Admin Terminal
=========================
Çalıştır:
  cd backend
  python admin_terminal.py --help
  python admin_terminal.py scan --market crypto --top 20
  python admin_terminal.py analyze BTC-USD
  python admin_terminal.py model train
  python admin_terminal.py firebase stats
  python admin_terminal.py server start

Gereksinimler: pip install typer rich
"""
from __future__ import annotations
import os
import sys
import json
import asyncio
import logging
from datetime import datetime
from typing import Optional, List

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.markup import escape

# Backend root
sys.path.insert(0, os.path.dirname(__file__))

console = Console()
app     = typer.Typer(
    name="optitrade-admin",
    help="[bold cyan]OptiTrade Admin Terminal[/bold cyan] — Backend yönetim arayüzü",
    rich_markup_mode="rich",
    no_args_is_help=True,
)

# Alt komut grupları
scan_app    = typer.Typer(help="Piyasa tarama komutları")
analyze_app = typer.Typer(help="Sembol analiz komutları")
model_app   = typer.Typer(help="AI model komutları")
firebase_app = typer.Typer(help="Firebase yönetim komutları")
server_app  = typer.Typer(help="Backend sunucu komutları")

app.add_typer(scan_app,      name="scan")
app.add_typer(analyze_app,   name="analyze")
app.add_typer(model_app,     name="model")
app.add_typer(firebase_app,  name="firebase")
app.add_typer(server_app,    name="server")

news_app = typer.Typer(help="Haber duygu analizi komutları")
app.add_typer(news_app, name="news")


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Yardımcı Fonksiyonlar
# ─────────────────────────────────────────────────────────────────────────────

def _header(title: str):
    console.print(Panel.fit(
        f"[bold cyan]{title}[/bold cyan]",
        border_style="cyan",
        subtitle=f"[dim]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]",
    ))


def _signal_color(signal: str) -> str:
    return {"BUY": "green", "SELL": "red", "NEUTRAL": "yellow",
            "HOLD": "yellow"}.get(signal.upper() if signal else "", "white")


def _score_bar(score: float, max_score: float = 100) -> str:
    pct   = max(0, min(1, score / max_score))
    bars  = int(pct * 20)
    color = "green" if pct > 0.6 else ("yellow" if pct > 0.35 else "red")
    return f"[{color}]{'█' * bars}{'░' * (20 - bars)}[/{color}] [dim]{score:.0f}[/dim]"


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - SCAN Komutları
# ─────────────────────────────────────────────────────────────────────────────

@scan_app.command("market")
def scan_market(
    market: str = typer.Option("crypto", "--market", "-m",
                                help="Piyasa: crypto | forex | stocks | indices"),
    top: int = typer.Option(20, "--top", "-n", help="Kaç sembol taransın"),
    min_score: float = typer.Option(50.0, "--min-score", help="Minimum skor filtresi"),
    signal: Optional[str] = typer.Option(None, "--signal", "-s",
                                          help="Sadece bu sinyal: BUY|SELL|NEUTRAL"),
    export: Optional[str] = typer.Option(None, "--export", "-o",
                                          help="JSON dosyasına kaydet"),
):
    """Piyasa taraması yap ve sinyalleri göster."""
    _header(f"Piyasa Taraması — {market.upper()}")

    MARKET_SYMBOLS = {
        "crypto": [
            "BTC-USD","ETH-USD","BNB-USD","SOL-USD","XRP-USD",
            "ADA-USD","DOGE-USD","AVAX-USD","LINK-USD","MATIC-USD",
            "DOT-USD","SHIB-USD","LTC-USD","BCH-USD","ATOM-USD",
            "UNI-USD","NEAR-USD","ICP-USD","FIL-USD","APT-USD",
        ],
        "forex": [
            "EURUSD=X","GBPUSD=X","USDJPY=X","AUDUSD=X","USDCAD=X",
            "USDCHF=X","NZDUSD=X","EURGBP=X","EURJPY=X","GBPJPY=X",
        ],
        "stocks": [
            "AAPL","MSFT","GOOGL","AMZN","NVDA",
            "META","TSLA","NFLX","AMD","INTC",
        ],
        "indices": ["^GSPC","^DJI","^IXIC","^RUT","^VIX"],
    }

    symbols = MARKET_SYMBOLS.get(market.lower(), MARKET_SYMBOLS["crypto"])[:top]
    results = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"Taranıyor ({len(symbols)} sembol)...", total=len(symbols))

        for sym in symbols:
            progress.update(task, advance=1, description=f"Analiz: [cyan]{sym}[/cyan]")
            try:
                from core.analyzer import FinancialAnalyzer
                analyzer = FinancialAnalyzer()
                result = asyncio.run(analyzer.analyze(sym))
                if result and "error" not in result:
                    rec_signal = result.get("recommendation", {}).get("signal", "N/A")
                    score      = result.get("score", {}).get("total", 0)

                    if signal and rec_signal.upper() != signal.upper():
                        continue
                    if score < min_score:
                        continue

                    results.append({
                        "symbol": sym,
                        "signal": rec_signal,
                        "score":  score,
                        "price":  result.get("current_price"),
                        "change": result.get("price_change_pct"),
                        "rsi":    result.get("indicators", {}).get("rsi"),
                    })
            except Exception as e:
                console.print(f"  [dim red]{sym}: {e}[/dim red]")

    results.sort(key=lambda x: x["score"], reverse=True)

    table = Table(title=f"Tarama Sonuçları — {len(results)} sonuç", border_style="cyan")
    table.add_column("#",       style="dim",   width=4)
    table.add_column("Sembol",  style="bold",  min_width=12)
    table.add_column("Sinyal",  min_width=10)
    table.add_column("Skor",    min_width=25)
    table.add_column("Fiyat",   justify="right", min_width=10)
    table.add_column("Değişim", justify="right", min_width=8)
    table.add_column("RSI",     justify="right", min_width=6)

    for i, r in enumerate(results, 1):
        sig   = r["signal"]
        color = _signal_color(sig)
        chg   = r.get("change", 0) or 0
        chg_str = f"[{'green' if chg >= 0 else 'red'}]{chg:+.2f}%[/]"
        rsi   = r.get("rsi")
        rsi_str = f"{rsi:.1f}" if rsi else "-"
        price = r.get("price")
        price_str = f"{price:,.4f}" if price else "-"

        table.add_row(
            str(i),
            r["symbol"],
            f"[{color}]{sig}[/{color}]",
            _score_bar(r["score"]),
            price_str,
            chg_str,
            rsi_str,
        )

    console.print(table)

    if export:
        with open(export, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        console.print(f"\n[green]Sonuçlar kaydedildi: {export}[/green]")


@scan_app.command("session")
def scan_session():
    """Mevcut seans bilgisini göster."""
    _header("Piyasa Seans Durumu")
    try:
        from core.session_analysis import get_current_session, get_session_multiplier
        session = get_current_session()
        sessions = [session.name]
        console.print(f"\nAktif Seanslar: [bold cyan]{', '.join(sessions) if sessions else 'Kapalı'}[/bold cyan]")
        multi = get_session_multiplier()
        console.print(f"Volatilite Çarpanı: [bold yellow]{multi:.2f}x[/bold yellow]\n")
    except ImportError as e:
        console.print(f"[yellow]Session modülü yüklenemedi: {e}[/yellow]")


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - ANALYZE Komutları
# ─────────────────────────────────────────────────────────────────────────────

@analyze_app.command("symbol")
def analyze_symbol(
    symbol: str = typer.Argument(..., help="Sembol (örn: BTC-USD, AAPL)"),
    enhanced: bool = typer.Option(False, "--enhanced", "-e", help="Gelişmiş analiz (Monte Carlo)"),
    patterns: bool = typer.Option(True,  "--patterns/--no-patterns", help="Formasyon analizi"),
    export: Optional[str] = typer.Option(None, "--export", "-o"),
):
    """Tek sembol için detaylı analiz."""
    _header(f"Analiz — {symbol}")

    with console.status(f"[cyan]{symbol}[/cyan] analiz ediliyor...", spinner="dots"):
        try:
            from core.analyzer import FinancialAnalyzer
            analyzer = FinancialAnalyzer()
            result   = asyncio.run(analyzer.analyze(symbol, enhanced=enhanced))
        except Exception as e:
            console.print(f"[bold red]Hata: {e}[/bold red]")
            raise typer.Exit(1)

    if not result or "error" in result:
        console.print(f"[red]Analiz başarısız: {result.get('error', 'Bilinmeyen hata')}[/red]")
        raise typer.Exit(1)

    # Ana bilgiler
    rec    = result.get("recommendation", {})
    score  = result.get("score", {})
    ind    = result.get("indicators", {})
    price  = result.get("current_price", 0)
    change = result.get("price_change_pct", 0)

    info_table = Table(show_header=False, box=None, padding=(0, 2))
    info_table.add_column(style="dim")
    info_table.add_column(style="bold")

    sig   = rec.get("signal", "N/A")
    color = _signal_color(sig)
    info_table.add_row("Fiyat",      f"{price:,.6g}")
    info_table.add_row("Değişim",    f"[{'green' if change >= 0 else 'red'}]{change:+.2f}%[/]")
    info_table.add_row("Sinyal",     f"[{color}]{sig}[/{color}]")
    info_table.add_row("Skor",       _score_bar(score.get("total", 0)))
    info_table.add_row("Güven",      f"{rec.get('confidence', 0):.1f}%")
    info_table.add_row("RSI",        f"{ind.get('rsi', 'N/A')}")
    info_table.add_row("MACD",       f"{ind.get('macd', 'N/A')}")
    info_table.add_row("BB %B",      f"{ind.get('bollinger_pb', 'N/A')}")

    console.print(Panel(info_table, title=f"[bold]{symbol}[/bold]", border_style=color))

    # Öneri
    advice = rec.get("advice", [])
    if advice:
        console.print("\n[bold]Yorumlar:[/bold]")
        for a in advice:
            console.print(f"  • {escape(a)}")

    # Formasyon
    if patterns:
        pat_result = result.get("patterns", {})
        detected   = pat_result.get("patterns", [])
        if detected:
            console.print(f"\n[bold]Formasyonlar:[/bold] [cyan]{', '.join(detected)}[/cyan]")
            for sig_msg in pat_result.get("signals", []):
                console.print(f"  • {escape(sig_msg)}")

    # Monte Carlo
    if enhanced:
        mc = result.get("monte_carlo", {})
        if mc:
            console.print(f"\n[bold]Monte Carlo (1000 simülasyon, 30 gün):[/bold]")
            console.print(f"  Beklenen Getiri : {mc.get('expected_return', 0):+.2f}%")
            console.print(f"  Risk (Std)      : {mc.get('std_return', 0):.2f}%")
            console.print(f"  %95 VaR         : {mc.get('var_95', 0):.2f}%")
            console.print(f"  Yükseliş Olasılığı: {mc.get('prob_positive', 0):.1f}%")

    if export:
        with open(export, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        console.print(f"\n[green]Kaydedildi: {export}[/green]")


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - MODEL Komutları
# ─────────────────────────────────────────────────────────────────────────────

@model_app.command("train")
def model_train(
    symbol: str = typer.Option(None, "--symbol", "-s", help="Sadece bu sembol için eğit"),
    market: str = typer.Option("ALL", "--market", "-m", help="Piyasa: ALL | BIST | US | NIKKEI"),
    epochs: int = typer.Option(50, "--epochs", "-e"),
    continuous: bool = typer.Option(False, "--continuous", help="Sürekli eğitim modunu başlat"),
    batch_size: int = typer.Option(64, "--batch-size", "-b"),
    period: str = typer.Option("max", "--period", help="Veri süresi"),
):
    """Global pazarlar için AI modelini eğit."""
    _header(f"Model Eğitimi — Market: {market} {('Symbol: ' + symbol) if symbol else ''}")

    if continuous:
        console.print("[bold yellow]Sürekli eğitim modu aktif. Model periyodik olarak güncellenecek.[/bold yellow]")
        # Burada bir loop veya cron job tetiklenebilir

    try:
        from research.train_chart_model import train
        # Market bazlı sembol filtreleme mantığı buraya eklenebilir
        meta = train(epochs=epochs, batch_size=batch_size, period=period)
        
        console.print(Panel(
            f"[bold green]✓ {market} Eğitimi Tamamlandı[/bold green]\n"
            f"Test Accuracy : [bold]{meta['test_accuracy']:.2%}[/bold]\n"
            f"Eğitilen Veri: {period}",
            title="Eğitim Özeti",
            border_style="green",
        ))
    except Exception as e:
        console.print(f"[bold red]Eğitim hatası: {e}[/bold red]")


@model_app.command("info")
def model_info():
    """Mevcut model bilgilerini göster."""
    _header("Model Bilgileri")
    try:
        from ml.chart_model import get_model_meta
        meta = get_model_meta()
        if not meta.get("available"):
            console.print("[yellow]Eğitilmiş model bulunamadı.[/yellow]")
            console.print("[dim]Eğitmek için: [bold]python admin_terminal.py model train[/bold][/dim]")
            return

        t = Table(show_header=False, box=None, padding=(0,2))
        t.add_column(style="dim")
        t.add_column(style="bold")
        t.add_row("Sembol",      meta.get("trained_on", "?"))
        t.add_row("Tarih",       meta.get("training_date", "?")[:19])
        t.add_row("Accuracy",    f"{meta.get('test_accuracy', 0):.2%}")
        t.add_row("Loss",        f"{meta.get('test_loss', 0):.4f}")
        t.add_row("Train/Val/Test", f"{meta.get('n_train',0):,} / {meta.get('n_val',0):,} / {meta.get('n_test',0):,}")
        t.add_row("Window",      f"{meta.get('window',60)} gün")
        t.add_row("Forward",     f"{meta.get('forward_days',5)} gün")
        console.print(Panel(t, title="CNN+LSTM Chart AI", border_style="cyan"))

        dist = meta.get("class_distribution", {})
        if dist:
            console.print(f"\nSınıf Dağılımı: BUY={dist.get('BUY',0):,}  "
                          f"NEUTRAL={dist.get('NEUTRAL',0):,}  "
                          f"SELL={dist.get('SELL',0):,}")
    except Exception as e:
        console.print(f"[red]Hata: {e}[/red]")


@model_app.command("predict")
def model_predict(
    symbol: str = typer.Argument(..., help="Sembol (örn: BTC-USD)"),
):
    """Chart AI modeliyle tahmin yap."""
    _header(f"AI Tahmin — {symbol}")
    try:
        import yfinance as yf
        from ml.chart_model import predict_chart_signal

        with console.status(f"[cyan]{symbol}[/cyan] verisi alınıyor..."):
            hist = yf.Ticker(symbol).history(period="3mo")

        if hist.empty:
            console.print("[red]Veri alınamadı.[/red]")
            raise typer.Exit(1)

        with console.status("Tahmin yapılıyor..."):
            result = predict_chart_signal(hist)

        if not result.get("model_available"):
            console.print("[yellow]Model henüz eğitilmedi.[/yellow]")
            console.print("[dim]Eğitmek için: [bold]python admin_terminal.py model train[/bold][/dim]")
            return

        sig   = result.get("signal", "N/A")
        conf  = result.get("confidence", 0)
        probs = result.get("probabilities", {})
        color = _signal_color(sig)

        console.print(Panel(
            f"Sinyal    : [{color}][bold]{sig}[/bold][/{color}]\n"
            f"Güven     : [bold]{conf:.2%}[/bold]\n"
            f"BUY prob  : [green]{probs.get('buy', 0):.2%}[/green]\n"
            f"NEUTRAL   : [yellow]{probs.get('neutral', 0):.2%}[/yellow]\n"
            f"SELL prob : [red]{probs.get('sell', 0):.2%}[/red]",
            title=f"AI Tahmin — {symbol}",
            border_style=color,
        ))
    except Exception as e:
        console.print(f"[bold red]Hata: {e}[/bold red]")
        raise typer.Exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - FIREBASE Komutları
# ─────────────────────────────────────────────────────────────────────────────

@firebase_app.command("stats")
def firebase_stats():
    """Firebase kullanıcı ve koleksiyon istatistiklerini göster."""
    _header("Firebase İstatistikleri")
    try:
        from firebase_admin import firestore

        db  = firestore.client()
        collections = ["users", "watchlists", "portfolios", "analyses", "alerts"]

        table = Table(title="Koleksiyon Özeti", border_style="cyan")
        table.add_column("Koleksiyon", style="bold")
        table.add_column("Belge Sayısı", justify="right")
        table.add_column("Durum")

        for col in collections:
            try:
                docs  = list(db.collection(col).limit(500).stream())
                count = len(docs)
                table.add_row(col, str(count), "[green]OK[/green]")
            except Exception as e:
                table.add_row(col, "-", f"[red]{e}[/red]")

        console.print(table)
    except Exception as e:
        console.print(f"[yellow]Firebase bağlantısı: {e}[/yellow]")
        console.print("[dim]GOOGLE_APPLICATION_CREDENTIALS ortam değişkenini ayarlayın.[/dim]")


@firebase_app.command("create-admin")
def firebase_create_admin(
    email: str = typer.Argument(..., help="Admin e-posta adresi"),
    password: str = typer.Argument(..., help="Admin şifresi"),
    display_name: str = typer.Option("Admin User", "--name", "-n"),
):
    """Yeni bir admin kullanıcısı oluştur (Auth + Firestore)."""
    _header(f"Admin Oluşturma — {email}")
    try:
        from firebase_admin import auth, firestore
        
        # 1. Create Auth User
        try:
            user = auth.create_user(
                email=email,
                password=password,
                display_name=display_name
            )
            console.print(f"[green]✓ Firebase Auth kullanıcısı oluşturuldu: {user.uid}[/green]")
        except Exception as e:
            if "EMAIL_EXISTS" in str(e):
                user = auth.get_user_by_email(email)
                console.print(f"[yellow]! Kullanıcı zaten mevcut, UID: {user.uid}[/yellow]")
            else:
                raise e

        # 2. Create/Update Firestore Profile
        db = firestore.client()
        profile_data = {
            "uid": user.uid,
            "email": email,
            "displayName": display_name,
            "isAdmin": True,
            "isPremium": True,
            "subscriptionLevel": "TRADE",
            "defaultAssetType": "stock",
            "showNeutralInScan": True,
            "focusAssets": ["BTC-USD", "ETH-USD", "AAPL"],
            "appTheme": "dark",
            "createdAt": firestore.SERVER_TIMESTAMP,
            "updatedAt": firestore.SERVER_TIMESTAMP,
        }
        db.collection("users").document(user.uid).set(profile_data, merge=True)
        console.print(f"[green]✓ Firestore admin profili hazırlandı.[/green]")
        
        console.print(Panel(
            f"E-posta: [bold]{email}[/bold]\nŞifre  : [bold]{password}[/bold]\nUID    : {user.uid}",
            title="Admin Giriş Bilgileri",
            border_style="green"
        ))

    except Exception as e:
        console.print(f"[bold red]Hata: {e}[/bold red]")


@firebase_app.command("export")
def firebase_export(
    collection: str = typer.Argument(..., help="Koleksiyon adı"),
    output: str = typer.Option("export.json", "--output", "-o"),
):
    """Firebase koleksiyonunu JSON'a aktar."""
    _header(f"Firebase Export — {collection}")
    try:
        from firebase_admin import firestore
        db   = firestore.client()
        docs = list(db.collection(collection).stream())
        data = [{"id": d.id, **d.to_dict()} for d in docs]

        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        console.print(f"[green]{len(data)} belge → {output}[/green]")
    except Exception as e:
        console.print(f"[red]Hata: {e}[/red]")


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - SERVER Komutları
# ─────────────────────────────────────────────────────────────────────────────

@server_app.command("start")
def server_start(
    host: str = typer.Option("0.0.0.0", "--host"),
    port: int = typer.Option(8000,      "--port", "-p"),
    reload: bool = typer.Option(False,  "--reload", "-r"),
    workers: int = typer.Option(1,      "--workers", "-w"),
):
    """FastAPI backend sunucusunu başlat."""
    _header(f"Sunucu Başlatılıyor — {host}:{port}")
    import subprocess
    cmd = [
        sys.executable, "-m", "uvicorn", "main:app",
        "--host", host, "--port", str(port),
        "--workers", str(workers),
    ]
    if reload:
        cmd += ["--reload"]

    console.print(f"[dim]Komut: {' '.join(cmd)}[/dim]\n")
    try:
        subprocess.run(cmd, cwd=os.path.dirname(__file__), check=True)
    except KeyboardInterrupt:
        console.print("\n[yellow]Sunucu durduruldu.[/yellow]")


@server_app.command("health")
def server_health(
    host: str = typer.Option("localhost", "--host"),
    port: int = typer.Option(8000, "--port", "-p"),
):
    """Backend sağlık kontrolü."""
    import urllib.request
    import urllib.error
    url = f"http://{host}:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
        console.print(Panel(
            f"[green]✓ Sunucu çalışıyor[/green]\n"
            f"Status : {data.get('status', 'OK')}\n"
            f"URL    : {url}",
            border_style="green",
        ))
    except Exception as e:
        console.print(Panel(
            f"[red]✗ Sunucuya erişilemiyor[/red]\n"
            f"URL   : {url}\n"
            f"Hata  : {e}",
            border_style="red",
        ))


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - NEWS Komutları
# ─────────────────────────────────────────────────────────────────────────────

@news_app.command("analyze")
def news_analyze(
    symbol: str = typer.Argument(..., help="Sembol (örn: BTC-USD, XOM, AAPL)"),
    show_headlines: bool = typer.Option(True, "--headlines/--no-headlines"),
    export: Optional[str] = typer.Option(None, "--export", "-o"),
):
    """Sembol için haber duygu analizi yap."""
    _header(f"Haber Analizi — {symbol}")
    with console.status(f"[cyan]{symbol}[/cyan] haberleri çekiliyor..."):
        try:
            from core.news_analyzer import get_news_summary
            result = get_news_summary(symbol.upper())
        except Exception as e:
            console.print(f"[red]Hata: {e}[/red]")
            raise typer.Exit(1)

    sentiment = result.get("sentiment_score", 0)
    label     = result.get("sentiment_label", "NEUTRAL")
    delta     = result.get("score_delta", 0)
    total     = result.get("total_news", 0)
    analyzed  = result.get("analyzed_news", 0)
    pos       = result.get("positive_count", 0)
    neg       = result.get("negative_count", 0)
    sector    = result.get("sector", "?")

    # Renk
    color = ("green" if sentiment > 0.1 else "red" if sentiment < -0.1 else "yellow")
    delta_str = f"[green]+{delta}[/green]" if delta > 0 else (f"[red]{delta}[/red]" if delta < 0 else "[dim]0[/dim]")

    info = Table(show_header=False, box=None, padding=(0, 2))
    info.add_column(style="dim", min_width=22)
    info.add_column(style="bold")
    info.add_row("Sektör",          sector)
    info.add_row("Toplam Haber",    str(total))
    info.add_row("Analiz Edilen",   str(analyzed))
    info.add_row("Duygu Skoru",     f"[{color}]{sentiment:+.3f}[/{color}]")
    info.add_row("Etiket",          f"[{color}]{label}[/{color}]")
    info.add_row("Skor Katkısı",    delta_str)
    info.add_row("Pozitif",         f"[green]{pos}[/green]")
    info.add_row("Negatif",         f"[red]{neg}[/red]")

    console.print(Panel(info, title=f"[bold]{symbol}[/bold] — Haber Özeti", border_style=color))

    # Sinyaller
    signals = result.get("signals", [])
    if signals:
        console.print("\n[bold]Haber Yorumları:[/bold]")
        for s in signals:
            prefix = "  [green]▲[/green]" if delta > 0 else ("  [red]▼[/red]" if delta < 0 else "  [dim]•[/dim]")
            console.print(f"{prefix} {escape(s)}")

    # Başlıklar
    if show_headlines:
        headlines = result.get("headlines", [])
        if headlines:
            console.print()
            ht = Table(title="Öne Çıkan Haberler", border_style="dim")
            ht.add_column("Duygu",   width=18)
            ht.add_column("Skor",    width=7, justify="right")
            ht.add_column("Başlık",  min_width=40)
            for h in headlines:
                lbl   = h["sentiment"]
                sc    = h["score"]
                hcol  = "green" if sc > 0.1 else ("red" if sc < -0.1 else "dim")
                ht.add_row(
                    f"[{hcol}]{lbl}[/{hcol}]",
                    f"[{hcol}]{sc:+.2f}[/{hcol}]",
                    h["title"][:80],
                )
            console.print(ht)

    if export:
        with open(export, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False, default=str)
        console.print(f"\n[green]Kaydedildi: {export}[/green]")


@news_app.command("sector")
def news_sector(
    sector: str = typer.Argument(..., help="Sektör: ENERGY | TECH | CRYPTO | FINANCE | HEALTH"),
    top: int = typer.Option(5, "--top", "-n", help="Kaç sembol analiz edilsin"),
):
    """Sektör bazlı toplu haber duygu analizi."""
    _header(f"Sektör Haber Analizi — {sector.upper()}")

    from core.sector_mapper import SECTOR_KEYWORDS
    sector_data = SECTOR_KEYWORDS.get(sector.upper())
    if not sector_data:
        available = list(SECTOR_KEYWORDS.keys())
        console.print(f"[red]Bilinmeyen sektör. Mevcut: {available}[/red]")
        raise typer.Exit(1)

    symbols = sector_data.get("sector_symbols", [])[:top]
    if not symbols:
        console.print(f"[yellow]{sector} sektörü için sembol tanımlı değil.[/yellow]")
        raise typer.Exit()

    from core.news_analyzer import get_news_summary
    sector_scores = []

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as prog:
        task = prog.add_task("Haberler çekiliyor...", total=len(symbols))
        for sym in symbols:
            prog.update(task, advance=1, description=f"→ {sym}")
            try:
                r = get_news_summary(sym)
                sector_scores.append((sym, r["sentiment_score"], r["score_delta"],
                                      r["positive_count"], r["negative_count"],
                                      r["sentiment_label"]))
            except Exception:
                pass

    if not sector_scores:
        console.print("[red]Haber alınamadı.[/red]")
        return

    avg_sent = sum(s[1] for s in sector_scores) / len(sector_scores)
    total_pos = sum(s[3] for s in sector_scores)
    total_neg = sum(s[4] for s in sector_scores)
    color = "green" if avg_sent > 0.1 else ("red" if avg_sent < -0.1 else "yellow")

    # Sektör özet paneli
    console.print(Panel(
        f"Sektör Duygu: [{color}]{avg_sent:+.3f}[/{color}]\n"
        f"Pozitif Haberler: [green]{total_pos}[/green]  "
        f"Negatif Haberler: [red]{total_neg}[/red]",
        title=f"{sector.upper()} Sektör Özeti",
        border_style=color,
    ))

    # Sembol tablosu
    t = Table(border_style="dim")
    t.add_column("Sembol", style="bold")
    t.add_column("Duygu Skoru", justify="right")
    t.add_column("Katkı",       justify="right")
    t.add_column("Etiket")
    t.add_column("+ / -")

    for sym, sc, delta, pos, neg, lbl in sorted(sector_scores, key=lambda x: -x[1]):
        c   = "green" if sc > 0.1 else ("red" if sc < -0.1 else "dim")
        d_s = f"[green]+{delta}[/green]" if delta > 0 else (f"[red]{delta}[/red]" if delta < 0 else "0")
        t.add_row(
            sym,
            f"[{c}]{sc:+.3f}[/{c}]",
            d_s,
            f"[{c}]{lbl}[/{c}]",
            f"[green]{pos}[/green] / [red]{neg}[/red]",
        )
    console.print(t)


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Sektör Fırsat Analizi
# ─────────────────────────────────────────────────────────────────────────────

sector_app = typer.Typer(help="Sektör fırsat analizi komutları")
app.add_typer(sector_app, name="sectors")


@sector_app.command("overview")
def sectors_overview(
    market: str = typer.Option("US", "--market", "-m", help="TR | US"),
):
    """Tüm sektörlerin fırsat skorunu hesapla, sırala."""
    _header(f"Sektör Fırsat Analizi — {market.upper()}")

    from core.sector_intelligence import get_sector_overview

    with console.status("[cyan]Sektörler analiz ediliyor (paralel)...[/cyan]"):
        results = get_sector_overview(market=market.upper(), use_cache=False)

    t = Table(border_style="dim", title=f"{market.upper()} Sektör Özeti")
    t.add_column("Sektör",    style="bold")
    t.add_column("Fırsat",    justify="right")
    t.add_column("Etiket")
    t.add_column("Trend")
    t.add_column("Boğa/Top", justify="center")
    t.add_column("Risk")
    t.add_column("Öne Çıkanlar")

    for r in results:
        score_color = "green" if r.opportunity_score >= 65 else (
            "yellow" if r.opportunity_score >= 48 else "red")
        trend_map = {
            "STRONG_BULL": "[bold green]🚀 GÜÇLÜ YUKARI[/bold green]",
            "BULLISH":     "[green]📈 YÜKSELİŞ[/green]",
            "NEUTRAL":     "[yellow]➡️  NÖTR[/yellow]",
            "BEARISH":     "[red]📉 DÜŞÜŞ[/red]",
            "STRONG_BEAR": "[bold red]💥 GÜÇLÜ DÜŞÜŞ[/bold red]",
        }
        tops = ", ".join(s.replace(".IS", "") for s in r.top_symbols)
        t.add_row(
            f"{r.icon} {r.name_tr}",
            f"[{score_color}]{r.opportunity_score:.0f}/100[/{score_color}]",
            f"[{score_color}]{r.opportunity_label}[/{score_color}]",
            trend_map.get(r.trend, r.trend),
            f"{r.bullish_count}/{r.total_count}",
            r.risk,
            tops or "—",
        )
    console.print(t)

    if results:
        best = results[0]
        console.print(Panel(
            f"[bold]{best.icon} {best.name_tr}[/bold]\n{best.advice}",
            title="[green]En Yüksek Fırsat[/green]",
            border_style="green",
        ))


@sector_app.command("detail")
def sector_detail_cmd(
    sector_key: str = typer.Argument(..., help="Sektör: TECH | ENERGY | FINANCE | ..."),
    market: str = typer.Option("US", "--market", "-m"),
):
    """Bir sektörün tüm sembollerini detaylı analiz et."""
    from core.sector_intelligence import analyze_sector

    _header(f"Sektör Detay — {sector_key.upper()} ({market.upper()})")
    with console.status("[cyan]Analiz ediliyor...[/cyan]"):
        r = analyze_sector(sector_key.upper(), market=market.upper(), use_cache=False)

    console.print(Panel(
        f"Fırsat Skoru: [bold]{r.opportunity_score:.0f}/100[/bold]  "
        f"Trend: [bold]{r.trend}[/bold]\n"
        f"Teknik Ortalama: {r.avg_technical:.0f}  "
        f"Haber Katkısı: {r.avg_news_delta:+.1f}\n"
        f"{r.advice}",
        title=f"{r.icon} {r.name_tr}",
        border_style="cyan",
    ))

    t = Table(border_style="dim")
    t.add_column("Sembol")
    t.add_column("Fiyat",   justify="right")
    t.add_column("Değ%",    justify="right")
    t.add_column("RSI",     justify="right")
    t.add_column("Skor",    justify="right")
    t.add_column("Karar")
    t.add_column("Haber+/-", justify="right")

    for s in sorted(r.symbols, key=lambda x: (x.score or 0) + x.news_delta, reverse=True):
        if s.error:
            t.add_row(s.symbol, "—", "—", "—", "—", f"[red]{s.error[:20]}[/red]", "—")
            continue
        chg_c = "green" if (s.change_pct or 0) > 0 else "red"
        rsi_c = "red" if (s.rsi or 50) > 70 else ("green" if (s.rsi or 50) < 30 else "white")
        dec_map = {"BUY": "[green]AL[/green]", "SELL": "[red]SAT[/red]",
                   "STRONG_BUY": "[bold green]GÜÇLÜ AL[/bold green]",
                   "STRONG_SELL": "[bold red]GÜÇLÜ SAT[/bold red]"}
        t.add_row(
            s.symbol.replace(".IS", ""),
            f"{s.price:.2f}" if s.price else "—",
            f"[{chg_c}]{s.change_pct:+.2f}%[/{chg_c}]" if s.change_pct else "—",
            f"[{rsi_c}]{s.rsi:.0f}[/{rsi_c}]" if s.rsi else "—",
            str(s.score or "—"),
            dec_map.get(s.decision_code or "", s.decision_code or "NÖTR"),
            f"{s.news_delta:+d}" if s.news_delta else "0",
        )
    console.print(t)


# ─────────────────────────────────────────────────────────────────────────────
# MARK: - Ana komutlar (root)
# ─────────────────────────────────────────────────────────────────────────────

@app.command("status")
def status():
    """Sistem durum özeti."""
    _header("OptiTrade Sistem Durumu")

    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_column(style="dim", min_width=22)
    t.add_column(style="bold")

    # Backend modül kontrolü
    def check(label, module):
        try:
            __import__(module)
            t.add_row(label, "[green]✓ Yüklendi[/green]")
        except ImportError as e:
            t.add_row(label, f"[red]✗ Eksik: {e}[/red]")

    check("FastAPI",       "fastapi")
    check("yfinance",      "yfinance")
    check("pandas",        "pandas")
    check("numpy",         "numpy")
    check("scipy",         "scipy")
    check("sklearn",       "sklearn")
    check("tensorflow",    "tensorflow")
    check("firebase_admin","firebase_admin")
    check("typer",         "typer")
    check("rich",          "rich")

    # Model durumu
    try:
        from ml.chart_model import is_model_available, get_model_meta
        if is_model_available():
            meta = get_model_meta()
            t.add_row("Chart AI Modeli", f"[green]✓ Accuracy: {meta.get('test_accuracy', 0):.2%}[/green]")
        else:
            t.add_row("Chart AI Modeli", "[yellow]⚠ Henüz eğitilmedi[/yellow]")
    except Exception:
        t.add_row("Chart AI Modeli", "[dim]Kontrol edilemedi[/dim]")

    # XGBoost modeli
    try:
        from core.ml_predictor import is_model_available as xgb_avail
        if xgb_avail():
            t.add_row("XGBoost Model",  "[green]✓ Mevcut[/green]")
        else:
            t.add_row("XGBoost Model",  "[yellow]⚠ Eğitilmedi[/yellow]")
    except Exception:
        t.add_row("XGBoost Model",  "[dim]Kontrol edilemedi[/dim]")

    console.print(Panel(t, title="Bileşen Durumu", border_style="cyan"))


@app.command("quickscan")
def quickscan(
    symbols: List[str] = typer.Argument(..., help="Semboller (boşlukla ayır: BTC-USD ETH-USD)"),
):
    """Birden fazla sembolü hızlı analiz et."""
    _header("Hızlı Tarama")
    results = []

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        task = progress.add_task("Analiz...", total=len(symbols))
        for sym in symbols:
            progress.update(task, advance=1, description=f"→ {sym}")
            try:
                from core.analyzer import FinancialAnalyzer
                result = asyncio.run(FinancialAnalyzer().analyze(sym))
                if result and "error" not in result:
                    results.append({
                        "symbol": sym,
                        "signal": result.get("recommendation", {}).get("signal", "N/A"),
                        "score":  result.get("score", {}).get("total", 0),
                        "price":  result.get("current_price"),
                    })
            except Exception as e:
                console.print(f"  [red]{sym}: {e}[/red]")

    if results:
        table = Table(border_style="cyan")
        table.add_column("Sembol", style="bold")
        table.add_column("Sinyal")
        table.add_column("Skor", min_width=22)
        table.add_column("Fiyat", justify="right")

        for r in sorted(results, key=lambda x: x["score"], reverse=True):
            color = _signal_color(r["signal"])
            table.add_row(
                r["symbol"],
                f"[{color}]{r['signal']}[/{color}]",
                _score_bar(r["score"]),
                f"{r['price']:,.4g}" if r["price"] else "-",
            )
        console.print(table)


if __name__ == "__main__":
    app()
