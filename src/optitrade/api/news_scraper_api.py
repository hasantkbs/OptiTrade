
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from typing import List, Dict

# API uygulamasını başlat
app = FastAPI(
    title="OptiTrade News Scraper API",
    description="Haber sitelerinden veri çekmek için kullanılan bir API.",
    version="1.0.0"
)

# Haber makalesi için veri modeli
class NewsArticle:
    def __init__(self, title: str, link: str):
        self.title = title
        self.link = link

@app.get(
    "/scrape-cointeleraph",
    summary="CoinTelegraph'dan Bitcoin haberlerini çeker",
    response_description="Haber başlıkları ve linklerinin bir listesi",
    tags=["News Scrapers"]
)
def scrape_cointeleraph_news() -> List[Dict[str, str]]:
    """
    CoinTelegraph web sitesinin 'Bitcoin' kategorisinden en son haberlerin
    başlıklarını ve linklerini çeker. Bu sürüm, sitenin HTML yapısındaki
    değişikliklere karşı daha dayanıklıdır.

    - **Returns**: Her biri 'title' ve 'link' anahtarlarını içeren bir sözlük listesi.
    """
    URL = "https://cointelegraph.com/tags/bitcoin"
    try:
        response = requests.get(URL, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()  # HTTP hatalarını kontrol et
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=503, detail=f"Web sitesine erişilemedi: {e}")

    soup = BeautifulSoup(response.content, "html.parser")
    with open("debug_output.html", "w", encoding="utf-8") as f:
        f.write(soup.prettify())
    
    articles = []
    seen_links = set() # To avoid duplicate articles

    # Find all links within the main content that look like news articles
    main_content = soup.find('main')
    if not main_content:
        # Fallback if <main> tag is not found
        main_content = soup.body

    for link_tag in main_content.find_all('a', href=True):
        href = link_tag['href']
        
        # Check if it's a news article link and not a duplicate
        if href.startswith('/news/') and href not in seen_links:
            # Try to find the specific title span, otherwise fall back to the link text
            title_span = link_tag.find('span', class_='post-card-horizontal__title')
            if title_span:
                title = title_span.get_text(strip=True)
            else:
                title = link_tag.get_text(strip=True) # Fallback
            
            # Ensure we have a valid title
            if title:
                full_link = f"https://cointelegraph.com{href}"
                articles.append({"title": title, "link": full_link})
                seen_links.add(href)

    if not articles:
        raise HTTPException(status_code=404, detail="Hiç haber bulunamadı. Sitenin yapısı değişmiş olabilir veya scraping mantığı güncellenmelidir.")

    return articles

# API'yi doğrudan çalıştırmak için (test amaçlı)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
