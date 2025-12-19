"""
Visualization module - Generate stock analysis charts.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from datetime import datetime


def create_visualization(metrics: dict, score_data: dict, output_path: str) -> str:
    """Create comprehensive visualization of stock data."""
    ticker = metrics['ticker']
    
    hist = _generate_price_history(
        metrics['current_price'],
        metrics['fifty_two_week_high'],
        metrics['fifty_two_week_low'],
        metrics.get('volatility')
    )
    
    fig = plt.figure(figsize=(16, 12))
    gs = GridSpec(3, 3, figure=fig, hspace=0.3, wspace=0.3)
    
    # Color scheme
    colors = {
        'primary': '#2E86AB',
        'secondary': '#A23B72',
        'positive': '#28A745',
        'negative': '#DC3545',
        'neutral': '#6C757D'
    }
    
    # Create all chart components
    _plot_price_chart(fig, gs, hist, ticker, colors)
    _plot_score_gauge(fig, gs, score_data, colors)
    _plot_volume_chart(fig, gs, hist, colors)
    _plot_component_scores(fig, gs, score_data, colors)
    _plot_metrics_table(fig, gs, metrics)
    _plot_returns_distribution(fig, gs, hist, colors)
    _plot_52week_range(fig, gs, metrics, colors)
    _plot_summary(fig, gs, metrics)
    
    plt.suptitle(f'Stock Analysis Report: {ticker}', fontsize=16, fontweight='bold', y=0.98)
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    
    return output_path


def _generate_price_history(current_price, high_52w, low_52w, volatility=None, days=252):
    """Generate realistic-looking price history based on known data points."""
    np.random.seed(42)
    
    if volatility:
        daily_vol = volatility / 100 / np.sqrt(252)
    else:
        daily_vol = (high_52w - low_52w) / current_price / np.sqrt(252) / 4
    
    returns = np.random.normal(0, daily_vol, days)
    start_price = (current_price + low_52w) / 2
    
    prices = [start_price]
    for ret in returns[:-1]:
        mean_reversion = (current_price - prices[-1]) / current_price * 0.01
        new_price = prices[-1] * (1 + ret + mean_reversion)
        new_price = max(low_52w * 0.95, min(high_52w * 1.05, new_price))
        prices.append(new_price)
    
    prices.append(current_price)
    
    end_date = datetime.now()
    dates = pd.date_range(end=end_date, periods=len(prices), freq='B')
    
    return pd.DataFrame({
        'Date': dates,
        'Close': prices,
        'High': [p * (1 + abs(np.random.normal(0, 0.01))) for p in prices],
        'Low': [p * (1 - abs(np.random.normal(0, 0.01))) for p in prices],
        'Volume': [np.random.randint(10000000, 100000000) for _ in prices]
    }).set_index('Date')


def _plot_price_chart(fig, gs, hist, ticker, colors):
    """Plot price chart with moving averages."""
    ax = fig.add_subplot(gs[0, :2])
    ax.plot(hist.index, hist['Close'], label='Price', color=colors['primary'], linewidth=1.5)
    
    if len(hist) >= 50:
        ma50 = hist['Close'].rolling(window=50).mean()
        ax.plot(hist.index, ma50, label='50-day MA', color=colors['secondary'], linewidth=1, linestyle='--')
    if len(hist) >= 200:
        ma200 = hist['Close'].rolling(window=200).mean()
        ax.plot(hist.index, ma200, label='200-day MA', color='#F18F01', linewidth=1, linestyle='--')
    
    ax.fill_between(hist.index, hist['Close'], alpha=0.1, color=colors['primary'])
    ax.set_title(f'{ticker} - 1 Year Price History (Illustrative Trend)', fontsize=14, fontweight='bold')
    ax.set_ylabel('Price ($)')
    ax.legend(loc='upper left')
    ax.grid(True, alpha=0.3)


def _plot_score_gauge(fig, gs, score_data, colors):
    """Plot the score gauge."""
    ax = fig.add_subplot(gs[0, 2])
    score = score_data['total_score']
    
    sizes = [score, 100 - score]
    score_color = (
        colors['positive'] if score >= 60 
        else (colors['neutral'] if score >= 40 else colors['negative'])
    )
    
    ax.pie(sizes, colors=[score_color, '#E9ECEF'], startangle=90, wedgeprops=dict(width=0.3))
    ax.text(0, 0, f'{score:.0f}', ha='center', va='center', fontsize=36, fontweight='bold')
    ax.text(0, -0.35, score_data['recommendation'], ha='center', va='center', fontsize=12, fontweight='bold')
    ax.set_title('Buy Consideration Score', fontsize=14, fontweight='bold')


def _plot_volume_chart(fig, gs, hist, colors):
    """Plot volume chart."""
    ax = fig.add_subplot(gs[1, 0])
    bar_colors = [
        colors['positive'] if (hist['Close'].iloc[i] >= hist['Close'].iloc[i-1] if i > 0 else True)
        else colors['negative'] for i in range(len(hist))
    ]
    ax.bar(hist.index, hist['Volume'], color=bar_colors, alpha=0.7, width=1)
    ax.set_title('Trading Volume (Simulated)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Volume')
    ax.ticklabel_format(style='scientific', axis='y', scilimits=(6, 6))


def _plot_component_scores(fig, gs, score_data, colors):
    """Plot component scores bar chart."""
    ax = fig.add_subplot(gs[1, 1])
    components = list(score_data['component_scores'].keys())
    values = list(score_data['component_scores'].values())
    bar_colors = [
        colors['positive'] if v >= 60 
        else (colors['neutral'] if v >= 40 else colors['negative'])
        for v in values
    ]
    
    y_pos = np.arange(len(components))
    ax.barh(y_pos, values, color=bar_colors, alpha=0.8)
    ax.set_yticks(y_pos)
    ax.set_yticklabels([c.replace('_', ' ').title() for c in components])
    ax.set_xlim(0, 100)
    ax.set_xlabel('Score')
    ax.set_title('Score Breakdown', fontsize=12, fontweight='bold')
    ax.axvline(x=50, color='gray', linestyle='--', alpha=0.5)
    
    for i, v in enumerate(values):
        ax.text(v + 2, i, f'{v:.0f}', va='center', fontsize=10)


def _plot_metrics_table(fig, gs, metrics):
    """Plot key metrics table."""
    ax = fig.add_subplot(gs[1, 2])
    ax.axis('off')
    
    key_data = [
        ('P/E Ratio', _format_value(metrics.get('pe_ratio'), 'ratio')),
        ('Forward P/E', _format_value(metrics.get('forward_pe'), 'ratio')),
        ('PEG Ratio', _format_value(metrics.get('peg_ratio'), 'ratio')),
        ('Market Cap', _format_value(metrics.get('market_cap'), 'cap')),
        ('Profit Margin', _format_value(metrics.get('profit_margin'), 'pct')),
        ('ROE', _format_value(metrics.get('return_on_equity'), 'pct')),
        ('Revenue Growth', _format_value(metrics.get('revenue_growth'), 'pct')),
        ('Debt/Equity', _format_value(metrics.get('debt_to_equity'), 'ratio')),
        ('Dividend Yield', _format_value(metrics.get('dividend_yield'), 'pct')),
        ('Beta', _format_value(metrics.get('beta'), 'ratio')),
    ]
    
    table = ax.table(
        cellText=key_data, colLabels=['Metric', 'Value'],
        loc='center', cellLoc='left', colWidths=[0.6, 0.4]
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.2, 1.5)
    ax.set_title('Key Metrics', fontsize=12, fontweight='bold', y=0.95)


def _plot_returns_distribution(fig, gs, hist, colors):
    """Plot daily returns distribution."""
    ax = fig.add_subplot(gs[2, 0])
    daily_returns = hist['Close'].pct_change().dropna() * 100
    
    ax.hist(daily_returns, bins=50, color=colors['primary'], alpha=0.7, edgecolor='white')
    ax.axvline(x=0, color='black', linestyle='-', linewidth=1)
    ax.axvline(
        x=daily_returns.mean(), color=colors['secondary'], 
        linestyle='--', linewidth=1.5, label=f'Mean: {daily_returns.mean():.2f}%'
    )
    ax.set_title('Daily Returns Distribution', fontsize=12, fontweight='bold')
    ax.set_xlabel('Daily Return (%)')
    ax.set_ylabel('Frequency')
    ax.legend()


def _plot_52week_range(fig, gs, metrics, colors):
    """Plot 52-week range indicator."""
    ax = fig.add_subplot(gs[2, 1])
    
    low = metrics['fifty_two_week_low']
    high = metrics['fifty_two_week_high']
    current = metrics['current_price']
    position = (current - low) / (high - low) if high > low else 0.5
    
    ax.barh([0], [1], color='#E9ECEF', height=0.3)
    ax.barh([0], [position], color=colors['primary'], height=0.3)
    ax.scatter([position], [0], color=colors['secondary'], s=200, zorder=5, marker='v')
    
    ax.set_xlim(-0.1, 1.1)
    ax.set_ylim(-0.5, 0.5)
    ax.set_yticks([])
    ax.set_xticks([0, 0.5, 1])
    ax.set_xticklabels([
        f'${low:.2f}\n(52w Low)', 
        f'${(low+high)/2:.2f}', 
        f'${high:.2f}\n(52w High)'
    ])
    ax.set_title(f'52-Week Range (Current: ${current:.2f})', fontsize=12, fontweight='bold')


def _plot_summary(fig, gs, metrics):
    """Plot summary text box."""
    ax = fig.add_subplot(gs[2, 2])
    ax.axis('off')
    
    summary_text = f"""
    {metrics.get('name', metrics['ticker'])}
    Sector: {metrics.get('sector', 'N/A')}
    Industry: {metrics.get('industry', 'N/A')}
    
    Current Price: ${metrics['current_price']:.2f}
    Volatility: {metrics.get('volatility', 'N/A')}
    
    Analyst Target: {_format_value(metrics.get('target_price'), 'price')}
    Analyst Rating: {metrics.get('recommendation', 'N/A')}
    """
    
    ax.text(
        0.1, 0.9, summary_text, transform=ax.transAxes, fontsize=10,
        verticalalignment='top', fontfamily='monospace',
        bbox=dict(boxstyle='round', facecolor='#F8F9FA', alpha=0.8)
    )
    ax.set_title('Summary', fontsize=12, fontweight='bold')


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
