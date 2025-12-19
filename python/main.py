#!/usr/bin/env python3
"""
Stock Analysis Tool - Main Entry Point
Analyze stocks and get buy consideration scores with visualizations.

Usage:
    python main.py                  # Interactive mode
    python main.py AAPL             # Analyze single stock
    python main.py AAPL MSFT GOOGL  # Analyze multiple stocks
    python main.py TSLA -o ./reports  # Custom output directory
"""

import argparse
import os

# Handle imports whether run as module or directly
try:
    from stock_analyzer import analyze_stock, get_stock_data, print_report
except ModuleNotFoundError:
    from analyzer import analyze_stock
    from data_fetcher import get_stock_data
    from report import print_report


# Default output directory (results folder in same directory as this script)
DEFAULT_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')


def interactive_mode():
    """Run the analyzer in interactive mode."""
    # Create results directory if it doesn't exist
    os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
    
    print("\n" + "="*60)
    print("         STOCK ANALYSIS TOOL")
    print("="*60)
    print("\nThis tool analyzes stocks and provides:")
    print("  • Key financial metrics")
    print("  • Buy consideration score (0-100)")
    print("  • Visual analysis chart")
    print(f"\nCharts will be saved to: {DEFAULT_OUTPUT_DIR}")
    print("\nType 'quit' or 'exit' to stop.\n")
    
    while True:
        ticker = input("Enter stock ticker (e.g., AAPL, MSFT, GOOGL): ").strip().upper()
        
        if ticker.lower() in ['quit', 'exit', 'q']:
            print("\nGoodbye!")
            break
        
        if not ticker:
            print("Please enter a valid ticker symbol.\n")
            continue
        
        # Fetch and analyze
        metrics = get_stock_data(ticker)
        
        if metrics is None:
            print(f"\nCould not fetch data for '{ticker}'. Please check the ticker symbol.\n")
            continue
        
        try:
            result = analyze_stock(metrics, output_dir=DEFAULT_OUTPUT_DIR)
            print_report(result)
            print(f"📊 Chart saved to: {result['visualization_path']}\n")
        except Exception as e:
            print(f"Error analyzing {ticker}: {e}\n")
            continue
        
        another = input("Analyze another stock? (y/n): ").strip().lower()
        if another not in ['y', 'yes']:
            print("\nGoodbye!")
            break
        print()


def analyze_tickers(tickers: list, output_dir: str = None):
    """Analyze a list of tickers."""
    if output_dir is None:
        output_dir = DEFAULT_OUTPUT_DIR
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    for ticker in tickers:
        print(f"\n{'='*60}")
        metrics = get_stock_data(ticker)
        
        if metrics is None:
            print(f"Skipping {ticker} - could not fetch data.\n")
            continue
        
        try:
            result = analyze_stock(metrics, output_dir=output_dir)
            print_report(result)
            print(f"📊 Chart saved to: {result['visualization_path']}\n")
        except Exception as e:
            print(f"Error analyzing {ticker}: {e}\n")


def main():
    parser = argparse.ArgumentParser(
        description='Stock Analysis Tool - Analyze stocks and get buy consideration scores',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python main.py                    # Interactive mode
  python main.py AAPL               # Analyze Apple
  python main.py MSFT GOOGL AMZN    # Analyze multiple stocks
  python main.py TSLA -o ./reports  # Save to custom directory
        '''
    )
    
    parser.add_argument(
        'tickers', 
        nargs='*', 
        help='Stock ticker symbol(s) to analyze (e.g., AAPL MSFT GOOGL)'
    )
    
    parser.add_argument(
        '-o', '--output',
        default=None,
        help=f'Output directory for charts (default: results/)'
    )
    
    parser.add_argument(
        '-i', '--interactive',
        action='store_true',
        help='Run in interactive mode'
    )
    
    args = parser.parse_args()
    
    if not args.tickers or args.interactive:
        interactive_mode()
    else:
        analyze_tickers(args.tickers, args.output)


if __name__ == "__main__":
    main()