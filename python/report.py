"""
Reporting module - Generate text reports for stock analysis.
"""


def print_report(result: dict):
    """Print a formatted text report."""
    metrics = result['metrics']
    score = result['score']
    
    print("\n" + "="*60)
    print(f"  STOCK ANALYSIS REPORT: {result['ticker']}")
    print("="*60)
    
    print(f"\n{metrics.get('name', result['ticker'])}")
    print(f"Sector: {metrics.get('sector', 'N/A')} | Industry: {metrics.get('industry', 'N/A')}")
    
    _print_section("PRICE INFORMATION", [
        ("Current Price", f"${metrics['current_price']:.2f}"),
        ("52-Week High", f"${metrics.get('fifty_two_week_high', 0):.2f}"),
        ("52-Week Low", f"${metrics.get('fifty_two_week_low', 0):.2f}"),
        ("From 52W High", f"{metrics.get('distance_from_52w_high', 0):.1f}%"),
    ])
    
    _print_section("VALUATION METRICS", [
        ("P/E Ratio", _format_value(metrics.get('pe_ratio'), 'ratio')),
        ("Forward P/E", _format_value(metrics.get('forward_pe'), 'ratio')),
        ("PEG Ratio", _format_value(metrics.get('peg_ratio'), 'ratio')),
        ("Price/Book", _format_value(metrics.get('price_to_book'), 'ratio')),
        ("Market Cap", _format_value(metrics.get('market_cap'), 'cap')),
    ])
    
    _print_section("PROFITABILITY & GROWTH", [
        ("Profit Margin", _format_value(metrics.get('profit_margin'), 'pct')),
        ("Return on Equity", _format_value(metrics.get('return_on_equity'), 'pct')),
        ("Revenue Growth", _format_value(metrics.get('revenue_growth'), 'pct')),
        ("Earnings Growth", _format_value(metrics.get('earnings_growth'), 'pct')),
    ])
    
    _print_section("FINANCIAL HEALTH", [
        ("Debt/Equity", _format_value(metrics.get('debt_to_equity'), 'ratio')),
        ("Current Ratio", _format_value(metrics.get('current_ratio'), 'ratio')),
        ("Dividend Yield", _format_value(metrics.get('dividend_yield'), 'pct')),
        ("Beta", _format_value(metrics.get('beta'), 'ratio')),
    ])
    
    print(f"\n{'─'*60}")
    print("  BUY CONSIDERATION SCORE")
    print(f"{'─'*60}")
    print(f"  Overall Score:      {score['total_score']}/100")
    print(f"  Recommendation:     {score['recommendation']}")
    print(f"\n  Component Breakdown:")
    for component, value in score['component_scores'].items():
        weight = score['weights'][component]
        print(f"    {component.replace('_', ' ').title():20} {value:5.1f}/100 (weight: {weight}%)")
    
    print("\n" + "="*60)
    print("  DISCLAIMER: This is not financial advice. Always do your")
    print("  own research before making investment decisions.")
    print("="*60 + "\n")


def _print_section(title: str, items: list):
    """Print a section with title and items."""
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")
    for label, value in items:
        print(f"  {label + ':':<18} {value}")


def _format_value(val, fmt=''):
    """Format values for display."""
    if val is None:
        return 'N/A'
    if fmt == 'pct':
        return f'{val*100:.1f}%'
    if fmt == 'ratio':
        return f'{val:.2f}'
    if fmt == 'price':
        return f'${val:,.2f}'
    if fmt == 'cap':
        if val >= 1e12:
            return f'${val/1e12:.1f}T'
        elif val >= 1e9:
            return f'${val/1e9:.1f}B'
        elif val >= 1e6:
            return f'${val/1e6:.1f}M'
        return f'${val:,.0f}'
    return str(val)
