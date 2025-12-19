"""
Data fetching module - Retrieve stock data from Yahoo Finance.
"""

import numpy as np


def get_stock_data(ticker: str) -> dict:
    """
    Fetch stock data using yfinance library.
    Returns a metrics dictionary ready for analysis.
    """
    try:
        import yfinance as yf
    except ImportError:
        print("yfinance not installed. Install with: pip install yfinance")
        return None
    
    print(f"Fetching data for {ticker.upper()}...")
    stock = yf.Ticker(ticker)
    
    try:
        info = stock.info
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return None
    
    if not info or 'currentPrice' not in info and 'regularMarketPrice' not in info:
        print(f"Could not find data for ticker: {ticker}")
        return None
    
    # Get current price (try multiple fields)
    current_price = (
        info.get('currentPrice') or 
        info.get('regularMarketPrice') or 
        info.get('previousClose', 0)
    )
    
    # Get historical data for volatility calculation
    volatility = _calculate_volatility(stock)
    
    metrics = {
        'ticker': ticker.upper(),
        'name': info.get('longName') or info.get('shortName', ticker.upper()),
        'sector': info.get('sector', 'N/A'),
        'industry': info.get('industry', 'N/A'),
        'current_price': current_price,
        'previous_close': info.get('previousClose', current_price),
        'day_change': info.get('regularMarketChange', 0),
        'day_change_percent': info.get('regularMarketChangePercent', 0),
        'fifty_two_week_high': info.get('fiftyTwoWeekHigh', current_price * 1.1),
        'fifty_two_week_low': info.get('fiftyTwoWeekLow', current_price * 0.9),
        'market_cap': info.get('marketCap'),
        'pe_ratio': info.get('trailingPE'),
        'forward_pe': info.get('forwardPE'),
        'peg_ratio': info.get('pegRatio'),
        'price_to_book': info.get('priceToBook'),
        'profit_margin': info.get('profitMargins'),
        'return_on_equity': info.get('returnOnEquity'),
        'revenue_growth': info.get('revenueGrowth'),
        'earnings_growth': info.get('earningsGrowth'),
        'debt_to_equity': info.get('debtToEquity'),
        'current_ratio': info.get('currentRatio'),
        'dividend_yield': info.get('dividendYield'),
        'beta': info.get('beta'),
        'volatility': volatility,
        'target_price': info.get('targetMeanPrice'),
        'target_high': info.get('targetHighPrice'),
        'target_low': info.get('targetLowPrice'),
        'recommendation': info.get('recommendationKey'),
        'recommendation_mean': info.get('recommendationMean'),  # 1=Strong Buy, 5=Sell
        'number_of_analysts': info.get('numberOfAnalystOpinions'),
    }
    
    # Fetch news articles
    try:
        news = stock.news
        print(f"News data type: {type(news)}")
        print(f"News content: {news[:2] if news else 'None'}")
        
        if news and len(news) > 0:
            articles = []
            for article in news[:6]:
                # Handle new yfinance structure where data is nested in 'content'
                content = article.get('content', article)  # Fall back to article itself if no 'content' key
                
                # Get title
                title = content.get('title', '') or article.get('title', '')
                
                # Get publisher
                provider = content.get('provider', {})
                publisher = provider.get('displayName', '') if isinstance(provider, dict) else ''
                if not publisher:
                    publisher = article.get('publisher', '')
                
                # Get link
                canonical = content.get('canonicalUrl', {})
                link = canonical.get('url', '') if isinstance(canonical, dict) else ''
                if not link:
                    link = article.get('link', '') or article.get('url', '')
                
                # Get publish time
                pub_date = content.get('pubDate', '') or content.get('displayTime', '')
                if pub_date:
                    # Convert ISO date string to timestamp
                    from datetime import datetime
                    try:
                        dt = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                        published = int(dt.timestamp())
                    except:
                        published = 0
                else:
                    published = article.get('providerPublishTime', 0)
                
                art = {
                    'title': title,
                    'publisher': publisher,
                    'link': link,
                    'published': published,
                }
                
                if art['title']:  # Only add if we have a title
                    articles.append(art)
                    
            metrics['news'] = articles
            print(f"Processed {len(articles)} articles")
        else:
            metrics['news'] = []
    except Exception as e:
        print(f"Error fetching news: {e}")
        metrics['news'] = []
    
    return metrics


def _calculate_volatility(stock) -> float:
    """Calculate annualized volatility from historical data."""
    try:
        hist = stock.history(period="1y")
        if len(hist) > 0:
            daily_returns = hist['Close'].pct_change().dropna()
            return daily_returns.std() * np.sqrt(252) * 100
    except:
        pass
    return None