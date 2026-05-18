# VSN Analysis

A web-based stock analysis tool that provides buy consideration scores based on fundamental analysis.

## Features

- Real-time stock data from Yahoo Finance
- Buy consideration score (0-100) based on:
  - Valuation (P/E, PEG ratio)
  - Profitability (ROE, profit margins)
  - Growth (revenue & earnings growth)
  - Financial health (debt/equity, current ratio)
  - Technical factors (52-week position, volatility, beta)
- Key metrics display
- 52-week price range indicator

## Setup

### 1. Install Python dependencies

```bash
cd stock-analyzer
pip install -r requirements.txt
```

### 2. Start the server

```bash
cd python
python server.py
```

### 3. Open in browser

Go to: **http://localhost:5000**

## Usage

1. Enter a stock ticker symbol (e.g., AAPL, MSFT, GOOGL)
2. Click "ANALYZE"
3. View the results including:
   - Current price and daily change
   - Buy consideration score with recommendation
   - Score breakdown by category
   - Key financial metrics
   - 52-week price range position

## Project Structure

```
stock-analyzer/
├── index.html          # Frontend UI
├── requirements.txt    # Python dependencies
├── README.md          # This file
└── python/
    ├── server.py       # Flask API server
    ├── data_fetcher.py # Yahoo Finance data fetching
    ├── scoring.py      # Buy score calculation
    ├── analyzer.py     # Main analysis logic
    ├── report.py       # Text report generation
    └── visualization.py # Chart generation
```

## API Endpoints

- `GET /` - Serves the main HTML page
- `GET /api/analyze/<TICKER>` - Returns JSON with stock analysis
- `GET /api/health` - Health check

## Disclaimer

This tool is for informational purposes only and should not be considered financial advice. Always conduct your own research before making investment decisions.
