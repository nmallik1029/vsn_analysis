# VSN Analysis

VSN Analysis is a stock research web app built around cleaner market pages, watchlists, community posts, and an AI-assisted screener. The goal is simple: make it easier to follow stocks without opening five different tools just to understand what is going on.

This repo contains the Flask app, HTML templates, static assets, Supabase-backed account and community features, and the Cloudflare Worker/container setup used for deployment.

## What is included

- Public home page with VSN branding and legal/footer pages
- Email and Google auth through Supabase
- Account settings with avatar upload, username, profile links, privacy settings, password reset, logout, and deletion
- Market pages with stock search and Lightweight Charts
- Full screen stock charts
- Watchlists
- Community feed, posts, comments, likes, reposts, followers, following lists, and user profiles
- Screener with factor scores and optional Gemini-powered VSN analysis
- Admin and moderator pages

## Tech stack

- Python 3.11
- Flask
- Supabase Auth, Postgres, and Storage
- Yahoo Finance style market data through Python fetchers
- TradingView Lightweight Charts on the frontend
- Gemini for AI screener reasoning when configured
- Cloudflare Workers plus Containers for production deploys

## Local setup

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Install Node dependencies for Wrangler:

```bash
npm install
```

Run the Flask app locally:

```bash
cd python
python server.py
```

Open:

```text
http://localhost:5000
```

## Environment variables

The app has development defaults for some values, but production should use real secrets through the environment.

Useful variables:

```text
SECRET_KEY
SUPABASE_URL
SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY
LLM_PROVIDER
GEMINI_API_KEY
GEMINI_MODEL
GEMINI_MAX_OUTPUT_TOKENS
OPENAI_API_KEY
CLOUDFLARE_API_TOKEN
CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_SITE_TAG
ADMIN_EMAILS
MODERATOR_EMAILS
```

For Cloudflare, set secrets with Wrangler:

```bash
npx wrangler secret put SUPABASE_ANON_KEY
npx wrangler secret put SUPABASE_SERVICE_ROLE_KEY
npx wrangler secret put SECRET_KEY
npx wrangler secret put GEMINI_API_KEY
```

## Deployment

The production deploy is configured in `wrangler.toml`.

Current routes:

```text
vsnanalysis.com/*
www.vsnanalysis.com/*
admin.vsnanalysis.com/*
```

Deploy with:

```bash
npm run deploy
```

or:

```bash
npx wrangler deploy
```

Cloudflare builds the container from `Dockerfile` and runs the Flask app with Gunicorn.

## Project layout

```text
stock-analyzer/
  python/
    server.py              Main Flask server and routes
    data_fetcher.py        Stock data fetching
    scoring.py             Screener and scoring logic
    analyzer.py            Analysis helpers
    report.py              Report generation helpers
    visualization.py       Chart generation helpers
  templates/               HTML templates
  static/                  CSS, images, logos, and browser assets
  worker/
    index.ts               Cloudflare Worker container entry
  scripts/                 Utility scripts
  Dockerfile               Production container
  wrangler.toml            Cloudflare deploy config
  requirements.txt         Python dependencies
  package.json             Wrangler scripts
```

## Useful pages

```text
/                       Home
/auth                   Sign in and sign up
/markets                Markets
/chart/<ticker>         Full screen stock chart
/watchlist              Watchlists
/screener               Market screener
/screener/<ticker>      Ticker screener page
/community              Community feed
/profile                Account settings
/privacy                Privacy Policy
/terms                  Terms and Conditions
/disclaimer             Financial disclaimer
/contact                Contact
```

## Notes

VSN Analysis is for informational and educational use. It is not financial advice. Market data, AI output, community posts, and screen scores can be wrong, delayed, incomplete, or unavailable. Always verify important information before making investment decisions.
