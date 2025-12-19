import json

with open("all_tickers.txt", "r") as f:
    tickers = sorted(
        {line.strip().upper() for line in f if line.strip()}
    )

with open("../python/tickers.json", "w") as f:
    json.dump(tickers, f)

print(f"Saved {len(tickers)} tickers")
