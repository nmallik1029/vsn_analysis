"""
Data fetching module - Retrieve stock data from Finnhub API.
Much faster than yfinance (~200ms vs 2-5s per request).

Get your free API key at: https://finnhub.io/register
"""

import os
import requests
import numpy as np
from datetime import datetime, timedelta

# Get API key from environment variable or use default (replace with your key)
FINNHUB_API_KEY = os.environ.get('FINNHUB_API_KEY', 'd50unjpr01qm94qodm90d50unjpr01qm94qodm9g')
FINNHUB_BASE_URL = 'https://finnhub.io/api/v1'


def get_stock_data(ticker: str) -> dict:
    """
    Fetch stock data using Finnhub API.
    Returns a metrics dictionary ready for analysis.
    """
    ticker = ticker.upper()
    print(f"Fetching data for {ticker}...")
    
    if FINNHUB_API_KEY == 'YOUR_API_KEY_HERE':
        print("Warning: No Finnhub API key set. Get one free at https://finnhub.io/register")
        print("Set it as environment variable FINNHUB_API_KEY or update data_fetcher.py")
        return None
    
    try:
        # Fetch all data in parallel-ish (could use threading for true parallel)
        quote = _get_quote(ticker)
        profile = _get_company_profile(ticker)
        metrics = _get_basic_financials(ticker)
        recommendation = _get_recommendation(ticker)
        price_target = _get_price_target(ticker)
        news = _get_news(ticker)
        candles = _get_candles(ticker)
        
        if not quote or quote.get('c', 0) == 0:
            print(f"Could not find data for ticker: {ticker}")
            return None
        
        current_price = quote.get('c', 0)  # Current price
        previous_close = quote.get('pc', current_price)  # Previous close
        
        # Calculate 52-week high/low from candles or metrics
        high_52w = current_price * 1.1  # Default
        low_52w = current_price * 0.9   # Default
        
        if candles and candles.get('h'):
            high_52w = max(candles['h']) if candles['h'] else high_52w
            low_52w = min(candles['l']) if candles['l'] else low_52w
        
        if metrics:
            high_52w = metrics.get('52WeekHigh', high_52w) or high_52w
            low_52w = metrics.get('52WeekLow', low_52w) or low_52w
        
        # Calculate volatility from candles
        volatility = _calculate_volatility(candles)
        
        # Build metrics dictionary
        result = {
            'ticker': ticker,
            'name': profile.get('name', ticker) if profile else ticker,
            'sector': profile.get('finnhubIndustry', 'N/A') if profile else 'N/A',
            'industry': profile.get('finnhubIndustry', 'N/A') if profile else 'N/A',
            'current_price': current_price,
            'previous_close': previous_close,
            'day_change': quote.get('d', 0),  # Day change
            'day_change_percent': quote.get('dp', 0),  # Day change percent
            'fifty_two_week_high': high_52w,
            'fifty_two_week_low': low_52w,
            'market_cap': profile.get('marketCapitalization', 0) * 1_000_000 if profile else None,  # Finnhub returns in millions
            
            # Valuation metrics
            'pe_ratio': _get_metric(metrics, 'peBasicExclExtraTTM', 'peTTM'),
            'forward_pe': _get_metric(metrics, 'peNormalizedAnnual'),
            'peg_ratio': _get_metric(metrics, 'pegRatio'),
            'price_to_book': _get_metric(metrics, 'pbQuarterly', 'pbAnnual'),
            
            # Profitability
            'profit_margin': _get_metric(metrics, 'netProfitMarginTTM', 'netProfitMarginAnnual'),
            'return_on_equity': _get_metric(metrics, 'roeTTM', 'roeRfy'),
            'revenue_growth': _get_metric(metrics, 'revenueGrowthTTMYoy', 'revenueGrowth3Y'),
            'earnings_growth': _get_metric(metrics, 'epsGrowthTTMYoy', 'epsGrowth3Y'),
            
            # Financial health
            'debt_to_equity': _get_metric(metrics, 'totalDebt/totalEquityQuarterly', 'totalDebt/totalEquityAnnual'),
            'current_ratio': _get_metric(metrics, 'currentRatioQuarterly', 'currentRatioAnnual'),
            'dividend_yield': _get_metric(metrics, 'dividendYieldIndicatedAnnual'),
            
            # Risk metrics
            'beta': _get_metric(metrics, 'beta'),
            'volatility': volatility,
            
            # Analyst data - Finnhub returns: targetHigh, targetLow, targetMean, targetMedian
            'target_price': _safe_get(price_target, 'targetMean', 'targetMedian'),
            'target_high': _safe_get(price_target, 'targetHigh'),
            'target_low': _safe_get(price_target, 'targetLow'),
            'recommendation': _map_recommendation(recommendation),
            'recommendation_mean': _get_recommendation_mean(recommendation),
            'number_of_analysts': _safe_get(price_target, 'numberOfAnalysts'),
            
            # News
            'news': news or [],
        }

        # Fallback to yfinance for analyst targets/recs if Finnhub missing them
        if (
            result.get('target_price') is None
            or result.get('target_high') is None
            or result.get('target_low') is None
            or result.get('recommendation') in (None, 'N/A')
        ):
            try:
                yf_data = get_stock_data_yfinance(ticker)
                if yf_data:
                    for key in ['target_price', 'target_high', 'target_low', 'recommendation', 'recommendation_mean', 'number_of_analysts']:
                        if result.get(key) in (None, 'N/A'):
                            result[key] = yf_data.get(key)
            except Exception as e:
                print(f"Fallback to yfinance failed: {e}")

        return result
        
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return None


def _finnhub_request(endpoint: str, params: dict = None) -> dict:
    """Make a request to Finnhub API."""
    if params is None:
        params = {}
    params['token'] = FINNHUB_API_KEY
    
    try:
        response = requests.get(f"{FINNHUB_BASE_URL}{endpoint}", params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            print("Rate limit hit. Finnhub free tier: 60 calls/minute")
        return None
    except requests.RequestException as e:
        print(f"Request error: {e}")
        return None


def _get_quote(ticker: str) -> dict:
    """Get current quote data."""
    return _finnhub_request('/quote', {'symbol': ticker})


def _get_company_profile(ticker: str) -> dict:
    """Get company profile."""
    return _finnhub_request('/stock/profile2', {'symbol': ticker})


def _get_basic_financials(ticker: str) -> dict:
    """Get basic financial metrics."""
    data = _finnhub_request('/stock/metric', {'symbol': ticker, 'metric': 'all'})
    return data.get('metric', {}) if data else {}


def _get_recommendation(ticker: str) -> list:
    """Get analyst recommendations."""
    return _finnhub_request('/stock/recommendation', {'symbol': ticker})


def _get_price_target(ticker: str) -> dict:
    """Get analyst price targets."""
    data = _finnhub_request('/stock/price-target', {'symbol': ticker})
    if data:
        print(f"Price target data: {data}")  # Debug log
    return data


def _get_news(ticker: str, days: int = 7) -> list:
    """Get recent news articles."""
    to_date = datetime.now().strftime('%Y-%m-%d')
    from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    data = _finnhub_request('/company-news', {
        'symbol': ticker,
        'from': from_date,
        'to': to_date
    })
    
    if not data:
        return []
    
    # Format news to match expected structure
    articles = []
    for article in data[:6]:  # Limit to 6 articles
        articles.append({
            'title': article.get('headline', ''),
            'publisher': article.get('source', ''),
            'link': article.get('url', ''),
            'published': article.get('datetime', 0),
        })
    
    return articles


def _get_candles(ticker: str, days: int = 365) -> dict:
    """Get historical price data (candles)."""
    to_time = int(datetime.now().timestamp())
    from_time = int((datetime.now() - timedelta(days=days)).timestamp())
    
    return _finnhub_request('/stock/candle', {
        'symbol': ticker,
        'resolution': 'D',  # Daily
        'from': from_time,
        'to': to_time
    })


def _calculate_volatility(candles: dict) -> float:
    """Calculate annualized volatility from candle data."""
    if not candles or candles.get('s') != 'ok' or not candles.get('c'):
        return None
    
    try:
        closes = np.array(candles['c'])
        if len(closes) < 20:
            return None
        
        # Calculate daily returns
        daily_returns = np.diff(closes) / closes[:-1]
        
        # Annualized volatility (std * sqrt(252))
        volatility = np.std(daily_returns) * np.sqrt(252) * 100
        return round(volatility, 2)
    except Exception:
        return None


def _get_metric(metrics: dict, *keys) -> float:
    """Get first available metric from multiple possible keys."""
    if not metrics:
        return None
    
    for key in keys:
        val = metrics.get(key)
        if val is not None and val != 0:
            # Convert percentages if needed (Finnhub returns some as decimals, some as percentages)
            if 'margin' in key.lower() or 'yield' in key.lower() or 'roe' in key.lower():
                if val > 1:  # Likely a percentage, convert to decimal
                    val = val / 100
            return val
    return None


def _safe_get(data: dict, *keys):
    """Safely get first available key from a dict that might be None."""
    if not data:
        return None
    for key in keys:
        val = data.get(key)
        if val is not None:
            return val
    return None


def _map_recommendation(recommendations: list) -> str:
    """Map recommendation data to a simple string."""
    if not recommendations or len(recommendations) == 0:
        return 'N/A'
    
    latest = recommendations[0]
    buy = latest.get('buy', 0) + latest.get('strongBuy', 0)
    sell = latest.get('sell', 0) + latest.get('strongSell', 0)
    hold = latest.get('hold', 0)
    
    if buy > sell + hold:
        return 'buy'
    elif sell > buy + hold:
        return 'sell'
    else:
        return 'hold'


def _get_recommendation_mean(recommendations: list) -> float:
    """Calculate mean recommendation score (1=Strong Buy, 5=Sell)."""
    if not recommendations or len(recommendations) == 0:
        return None
    
    latest = recommendations[0]
    strong_buy = latest.get('strongBuy', 0)
    buy = latest.get('buy', 0)
    hold = latest.get('hold', 0)
    sell = latest.get('sell', 0)
    strong_sell = latest.get('strongSell', 0)
    
    total = strong_buy + buy + hold + sell + strong_sell
    if total == 0:
        return None
    
    # Weighted average (1=Strong Buy, 2=Buy, 3=Hold, 4=Sell, 5=Strong Sell)
    score = (strong_buy * 1 + buy * 2 + hold * 3 + sell * 4 + strong_sell * 5) / total
    return round(score, 2)


# Optional: Keep yfinance as fallback
def get_stock_data_yfinance(ticker: str) -> dict:
    """
    Fallback: Fetch stock data using yfinance library.
    Slower but doesn't require API key.
    """
    try:
        import yfinance as yf
    except ImportError:
        print("yfinance not installed. Install with: pip install yfinance")
        return None
    
    print(f"Fetching data for {ticker.upper()} via yfinance (slower)...")
    stock = yf.Ticker(ticker)
    
    try:
        info = stock.info
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return None
    
    if not info or 'currentPrice' not in info and 'regularMarketPrice' not in info:
        print(f"Could not find data for ticker: {ticker}")
        return None
    
    current_price = (
        info.get('currentPrice') or 
        info.get('regularMarketPrice') or 
        info.get('previousClose', 0)
    )
    
    # Calculate volatility
    volatility = None
    try:
        hist = stock.history(period="1y")
        if len(hist) > 0:
            daily_returns = hist['Close'].pct_change().dropna()
            volatility = daily_returns.std() * np.sqrt(252) * 100
    except:
        pass
    
    return {
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
        'recommendation_mean': info.get('recommendationMean'),
        'number_of_analysts': info.get('numberOfAnalystOpinions'),
        'news': [],
    }
