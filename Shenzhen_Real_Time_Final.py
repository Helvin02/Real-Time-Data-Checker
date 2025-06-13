import requests
import json
import pandas as pd
import time
import re
from datetime import datetime
from typing import Dict, List, Optional

class SZSEDataFetcher:
    def __init__(self):
        self.base_url = "http://qt.gtimg.cn/q="
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def format_symbol(self, symbol: str) -> str:
        """Format symbol for API call"""
        if symbol.startswith('300') or symbol.startswith('000') or symbol.startswith('002'):
            return f"sz{symbol}"
        elif symbol.startswith('60') or symbol.startswith('68'):
            return f"sh{symbol}"
        else:
            return f"sz{symbol}"
    
    def get_realtime_data(self, symbol: str, expected_data: Dict = None) -> Optional[Dict]:
        """
        Fetch real-time data for a single symbol
        Returns dictionary with stock data or None if failed
        expected_data: Dict with 'sid' and 'equ_open' keys
        """
        formatted_symbol = self.format_symbol(symbol)
        url = f"{self.base_url}{formatted_symbol}"
        
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            # Parse the response
            data_str = response.text.strip()
            if not data_str or 'pv_none_match' in data_str:
                print(f"No data available for symbol: {symbol}")
                return None
            
            # Extract data from the response string
            match = re.search(r'"([^"]*)"', data_str)
            if not match:
                return None
                
            data_parts = match.group(1).split('~')
            if len(data_parts) < 30:
                return None
            
            # Use provided expected data or fallback to default
            if expected_data is None:
                expected_data = {'sid': f'SID_{symbol}', 'equ_open': None}
            
            # Parse the data according to Tencent API format
            stock_data = {
                'sid': expected_data['sid'],
                'symbol': symbol,
                'name': data_parts[1],
                'code': data_parts[2],
                'current_price': float(data_parts[3]) if data_parts[3] else 0,
                'yesterday_close': float(data_parts[4]) if data_parts[4] else 0,
                'open': float(data_parts[5]) if data_parts[5] else 0,
                'open_equ_prices': expected_data['equ_open'],
                'volume': int(data_parts[6]) if data_parts[6] else 0,  # in lots (100 shares)
                'volume_shares': int(data_parts[6]) * 100 if data_parts[6] else 0,  # in shares
                'turnover': float(data_parts[37]) if len(data_parts) > 37 and data_parts[37] else 0,
                'bid1_price': float(data_parts[9]) if data_parts[9] else 0,
                'bid1_volume': int(data_parts[10]) if data_parts[10] else 0,
                'ask1_price': float(data_parts[19]) if data_parts[19] else 0,
                'ask1_volume': int(data_parts[20]) if data_parts[20] else 0,
                'high': float(data_parts[33]) if len(data_parts) > 33 and data_parts[33] else 0,
                'low': float(data_parts[34]) if len(data_parts) > 34 and data_parts[34] else 0,
                'change': float(data_parts[31]) if len(data_parts) > 31 and data_parts[31] else 0,
                'change_percent': float(data_parts[32]) if len(data_parts) > 32 and data_parts[32] else 0,
                'timestamp': data_parts[30] if len(data_parts) > 30 else '',
                'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # Add matching status
            if stock_data['open_equ_prices'] is not None:
                tolerance = 0.01  # 1 cent tolerance
                if abs(stock_data['open'] - stock_data['open_equ_prices']) <= tolerance:
                    stock_data['match_status'] = 'MATCHED!'
                else:
                    stock_data['match_status'] = 'NOT MATCHED!'
            else:
                stock_data['match_status'] = 'NO EXPECTED PRICE'
            
            return stock_data
            
        except requests.RequestException as e:
            print(f"Network error for symbol {symbol}: {e}")
            return None
        except Exception as e:
            print(f"Parsing error for symbol {symbol}: {e}")
            return None
    
    def get_multiple_symbols(self, symbols_data: List[Dict]) -> List[Dict]:
        """
        Fetch real-time data for multiple symbols with expected data
        symbols_data: List of dicts with 'symbol', 'sid', and 'equ_open' keys
        """
        results = []
        for symbol_info in symbols_data:
            symbol = symbol_info['symbol']
            expected_data = {'sid': symbol_info['sid'], 'equ_open': symbol_info['equ_open']}
            
            data = self.get_realtime_data(symbol, expected_data)
            if data:
                results.append(data)
            time.sleep(0.1)  # Small delay to avoid overwhelming the server
        return results
    
    def display_data(self, data: Dict):
        """Display formatted stock data"""
        print(f"\n{'='*60}")
        print(f"Stock: {data['name']} ({data['code']})")
        print(f"{'='*60}")
        print(f"SID: {data['sid']}")
        print(f"Symbol: {data['symbol']}")
        print(f"Current Price: ¥{data['current_price']:.2f}")
        print(f"Open: ¥{data['open']:.2f}")
        if data['open_equ_prices'] is not None:
            print(f"Open (equ_prices): ¥{data['open_equ_prices']:.2f}")
            print(f"Price Match Status: {data['match_status']}")
        else:
            print(f"Open (equ_prices): Not Available")
            print(f"Price Match Status: {data['match_status']}")
        print(f"High: ¥{data['high']:.2f}")
        print(f"Low: ¥{data['low']:.2f}")
        print(f"Previous Close: ¥{data['yesterday_close']:.2f}")
        print(f"Change: ¥{data['change']:.2f} ({data['change_percent']:.2f}%)")
        print(f"Volume: {data['volume']:,} lots ({data['volume_shares']:,} shares)")
        print(f"Turnover: ¥{data['turnover']:,.2f}")
        print(f"Bid1: ¥{data['bid1_price']:.2f} x {data['bid1_volume']}")
        print(f"Ask1: ¥{data['ask1_price']:.2f} x {data['ask1_volume']}")
        print(f"Last Update: {data['last_update']}")
        print(f"{'='*60}")
    
    def display_summary_table(self, data_list: List[Dict]):
        """Display summary table of multiple stocks"""
        if not data_list:
            print("No data to display.")
            return
        
        print(f"\n{'='*130}")
        print("SUMMARY TABLE")
        print(f"{'='*130}")
        
        # Create formatted table
        header = f"{'SID':<8} {'Symbol':<8} {'Name':<12} {'Open':<8} {'Equ_Open':<9} {'Match':<12} {'Current':<8} {'High':<8} {'Low':<8} {'Change%':<8} {'Volume':<12}"
        print(header)
        print("-" * len(header))
        
        for data in data_list:
            row = (f"{data['sid']:<8} "
                   f"{data['symbol']:<8} "
                   f"{data['name'][:10]:<12} "
                   f"{data['open']:<8.2f} "
                   f"{data['open_equ_prices'] if data['open_equ_prices'] is not None else 'N/A':<9} "
                   f"{data['match_status']:<12} "
                   f"{data['current_price']:<8.2f} "
                   f"{data['high']:<8.2f} "
                   f"{data['low']:<8.2f} "
                   f"{data['change_percent']:<8.2f} "
                   f"{data['volume']:<12,}")
            print(row)
    
    def create_dataframe(self, data_list: List[Dict]) -> pd.DataFrame:
        """Create pandas DataFrame from stock data"""
        if not data_list:
            return pd.DataFrame()
        
        df = pd.DataFrame(data_list)
        # Select and reorder columns including new fields
        columns = ['sid', 'symbol', 'name', 'current_price', 'open', 'open_equ_prices', 
                  'match_status', 'high', 'low', 'yesterday_close', 'change', 
                  'change_percent', 'volume', 'turnover', 'last_update']
        return df[columns]

def get_symbols_with_expected_data():
    """Get symbols with SID and expected open prices from user"""
    print("="*60)
    print("Enter stock data (SID, Symbol, Expected Open Price)")
    print("="*60)
    
    symbols_data = []
    
    while True:
        print(f"\nEntering stock #{len(symbols_data) + 1}:")
        print("(Press Enter on SID to finish)")
        
        # Get SID
        sid = input("Enter SID (e.g., SID001): ").strip()
        if not sid:
            break
            
        # Get Symbol
        while True:
            symbol = input("Enter Symbol (e.g., 300928): ").strip()
            if symbol.isdigit() and len(symbol) == 6:
                break
            else:
                print("Invalid symbol format. Please enter a 6-digit stock code.")
        
        # Get Expected Open Price
        while True:
            try:
                equ_price_input = input("Enter Expected Open (equ_price): ").strip()
                if not equ_price_input:
                    print("Please enter a valid price.")
                    continue
                equ_price = float(equ_price_input)
                break
            except ValueError:
                print("Invalid price format. Please enter a number (e.g., 34.11).")
        
        symbols_data.append({
            'sid': sid,
            'symbol': symbol,
            'equ_open': equ_price
        })
        
        print(f"✅ Added: {sid} - {symbol} - ¥{equ_price:.2f}")
        
        # Ask if user wants to add more
        continue_choice = input("\nAdd another stock? (y/n, default is y): ").strip().lower()
        if continue_choice in ['n', 'no']:
            break
    
    return symbols_data

def show_menu():
    """Display main menu options"""
    print("\n" + "="*40)
    print("Choose an option:")
    print("1. Check stock data with expected prices")
    print("2. Exit")
    print("="*40)

def main():
    """Main interactive function"""
    print("🔥 Interactive Shenzhen Stock Exchange Data Fetcher 🔥")
    print("Get real-time stock data and compare with expected prices!")
    
    fetcher = SZSEDataFetcher()
    
    while True:
        show_menu()
        choice = input("Enter your choice (1-2): ").strip()
        
        if choice == '1':
            # Get symbols with expected data
            symbols_data = get_symbols_with_expected_data()
            
            if not symbols_data:
                print("No stocks entered. Returning to main menu.")
                continue
            
            symbols = [data['symbol'] for data in symbols_data]
            print(f"\nFetching real-time data for: {', '.join(symbols)}")
            print("Comparing with your expected prices...")
            print("Please wait...")
            
            # Fetch data
            all_data = fetcher.get_multiple_symbols(symbols_data)
            
            if all_data:
                print(f"\n✅ Successfully fetched data for {len(all_data)} symbol(s)")
                
                # Show match summary first
                print(f"\n🔍 PRICE MATCH SUMMARY:")
                print("-" * 40)
                matched_count = 0
                for data in all_data:
                    status_emoji = "✅" if data['match_status'] == 'MATCHED!' else "❌"
                    print(f"{status_emoji} {data['symbol']} ({data['name'][:15]}): {data['match_status']}")
                    if data['match_status'] == 'MATCHED!':
                        matched_count += 1
                
                print(f"\n📊 Results: {matched_count}/{len(all_data)} symbols matched your expected prices")
                print("-" * 40)
                
                # Ask user how they want to view the data
                print("\nHow would you like to view the detailed data?")
                print("1. Detailed view (one by one)")
                print("2. Summary table")
                print("3. Both")
                print("4. Skip detailed view")
                
                view_choice = input("Enter choice (1-4, default is 3): ").strip()
                if not view_choice:
                    view_choice = '3'
                
                if view_choice in ['1', '3']:
                    # Display detailed data
                    for data in all_data:
                        fetcher.display_data(data)
                
                if view_choice in ['2', '3']:
                    # Display summary table
                    fetcher.display_summary_table(all_data)
                
                # Save to CSV option
                save_choice = input("\nSave data to CSV? (y/n, default is n): ").strip().lower()
                if save_choice in ['y', 'yes']:
                    df = fetcher.create_dataframe(all_data)
                    filename = f"stock_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                    df.to_csv(filename, index=False)
                    print(f"✅ Data saved to '{filename}'")
                
            else:
                print("❌ No data retrieved. Please check your symbols and try again.")
            
            # Ask if user wants to continue
            continue_choice = input("\nWould you like to check more stocks? (y/n): ").strip().lower()
            if continue_choice not in ['y', 'yes']:
                break
                
        elif choice == '2':
            print("Thank you for using the Stock Data Fetcher! 👋")
            break
        else:
            print("Invalid choice. Please enter 1 or 2.")

# Quick function for single symbol lookup with expected data
def quick_lookup(symbol: str, sid: str = None, expected_open: float = None):
    """Quick lookup for a single symbol with optional expected data"""
    fetcher = SZSEDataFetcher()
    
    expected_data = None
    if sid and expected_open:
        expected_data = {'sid': sid, 'equ_open': expected_open}
    
    data = fetcher.get_realtime_data(symbol, expected_data)
    if data:
        fetcher.display_data(data)
        return data
    else:
        print(f"No data found for symbol: {symbol}")
        return None

# Alternative function using akshare (if available)
def get_data_with_akshare(symbol: str):
    try:
        import akshare as ak
        
        # For Shenzhen stocks, use the symbol directly
        stock_info = ak.stock_zh_a_spot_em()
        
        # Filter for specific symbol
        stock_data = stock_info[stock_info['代码'] == symbol]
        
        if not stock_data.empty:
            return stock_data.iloc[0].to_dict()
        else:
            print(f"No data found for symbol: {symbol}")
            return None
            
    except ImportError:
        print("akshare library not installed. Install with: pip install akshare")
        return None
    except Exception as e:
        print(f"Error with akshare: {e}")
        return None

if __name__ == "__main__":
    main()