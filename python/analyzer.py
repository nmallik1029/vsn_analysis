"""
Core analyzer module - Main analysis logic.
"""

try:
    from .scoring import calculate_score
    from .visualization import create_visualization
    from .report import print_report
except ImportError:
    from scoring import calculate_score
    from visualization import create_visualization
    from report import print_report


def analyze_stock(metrics: dict, output_dir: str = '.') -> dict:
    """
    Main function to analyze a stock from provided metrics.
    
    Args:
        metrics: Dictionary with stock metrics
        output_dir: Directory to save the visualization
    
    Returns:
        Dictionary with ticker, metrics, score, and visualization path
    """
    ticker = metrics['ticker']
    
    print(f"Analyzing {ticker}...")
    
    # Calculate distance from 52-week high if not provided
    if 'distance_from_52w_high' not in metrics:
        high = metrics.get('fifty_two_week_high', metrics['current_price'])
        current = metrics['current_price']
        metrics['distance_from_52w_high'] = ((current - high) / high) * 100
    
    print("Calculating buy consideration score...")
    score_data = calculate_score(metrics)
    
    print("Generating visualization...")
    output_path = f"{output_dir}/{ticker.upper()}_analysis.png"
    create_visualization(metrics, score_data, output_path)
    
    return {
        'ticker': ticker.upper(),
        'metrics': metrics,
        'score': score_data,
        'visualization_path': output_path
    }