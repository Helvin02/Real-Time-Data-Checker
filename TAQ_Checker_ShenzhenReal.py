import requests
import json
import pandas as pd
import time
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

class SZSEOfficialDataFetcher:
    def __init__(self):
        self.historical_url = "https://www.szse.cn/api/report/ShowReport/data"
        self.current_url = "https://www.szse.cn/api/market/ssjjhq/getTimeData"
        self.session = requests.Session()
        self.session.headers.update({
            'Referer': 'https://www.szse.cn/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def pad_ticker(self, symbol: str) -> str:
        """Pad ticker to 6 digits if needed"""
        return symbol.zfill(6)
    
    def is_weekend(self, target_date: str) -> bool:
        """Check if the given date is a weekend"""
        try:
            date_obj = datetime.strptime(target_date, '%Y-%m-%d').date()
            # Monday = 0, Sunday = 6
            return date_obj.weekday() >= 5  # Saturday = 5, Sunday = 6
        except ValueError:
            return False
    
    def is_market_open_now(self) -> bool:
        """Check if SZSE market is currently open (Beijing time)"""
        try:
            # Get current Beijing time
            from datetime import timezone
            beijing_tz = timezone(timedelta(hours=8))
            now_beijing = datetime.now(beijing_tz)
            
            # Check if it's weekend
            if now_beijing.weekday() >= 5:  # Saturday = 5, Sunday = 6
                return False
            
            current_time = now_beijing.time()
            
            # SZSE trading hours (Beijing time):
            # Morning session: 9:30 AM - 11:30 AM
            # Afternoon session: 1:00 PM - 3:00 PM
            morning_start = datetime.strptime("09:30", "%H:%M").time()
            morning_end = datetime.strptime("11:30", "%H:%M").time()
            afternoon_start = datetime.strptime("13:00", "%H:%M").time()
            afternoon_end = datetime.strptime("15:00", "%H:%M").time()
            
            # Check if current time is within trading hours
            is_morning_session = morning_start <= current_time <= morning_end
            is_afternoon_session = afternoon_start <= current_time <= afternoon_end
            
            return is_morning_session or is_afternoon_session
            
        except Exception as e:
            print(f"⚠️ Could not determine market hours: {e}")
            # Default to assuming market is open if we can't determine
            return True
    
    def create_market_closed_result(self, symbol: str, expected_open: float, reason: str) -> Dict:
        """Create a result dict for when market is closed"""
        return {
            'symbol': symbol,
            'name': 'N/A',
            'open': 0.0,
            'expected_open': expected_open,
            'match_status': 'MARKET CLOSED',
            'data_type': reason,
            'market_status': reason
        }
    
    def get_date_mode(self, target_date: str = None) -> tuple:
        """
        Determine if we should fetch historical or current data
        Returns (mode, date_string)
        """
        if target_date is None:
            # No date specified, get current data
            current_date = datetime.now().strftime('%Y-%m-%d')
            
            # Check if market is open now
            if not self.is_market_open_now():
                return "market_closed_now", current_date
            
            return "current", current_date
        
        try:
            # Parse the target date
            target_dt = datetime.strptime(target_date, '%Y-%m-%d').date()
            today = date.today()
            
            if target_dt > today:
                return "invalid", target_date
            elif target_dt == today:
                # Check if market is open now for today's data
                if not self.is_market_open_now():
                    return "market_closed_now", target_date
                return "current", target_date
            else:
                # Historical date - check if it's weekend
                if self.is_weekend(target_date):
                    return "market_closed_weekend", target_date
                return "historical", target_date
        except ValueError:
            print(f"Invalid date format: {target_date}. Use YYYY-MM-DD format.")
            return "invalid", target_date
    
    def fetch_current_data(self, symbol: str) -> Optional[Dict]:
        """Fetch current/real-time data from SZSE API"""
        ticker_padded = self.pad_ticker(symbol)
        
        params = {
            "random": "0.123456",
            "marketId": "1",
            "code": ticker_padded,
            "language": "EN"
        }
        
        try:
            print(f"🔍 Fetching current data for {symbol} ({ticker_padded})")
            print(f"📡 API URL: {self.current_url}")
            print(f"📋 Parameters: {params}")
            
            response = self.session.get(self.current_url, params=params, timeout=10)
            response.raise_for_status()
            
            print(f"📄 Response Status: {response.status_code}")
            
            # Print raw response for debugging
            raw_response = response.text
            print(f"📄 Raw Response (first 500 chars): {raw_response[:500]}...")
            
            try:
                data = response.json()
                print(f"📊 Parsed JSON keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
                
                # More flexible data checking
                data_content = None
                if isinstance(data, dict):
                    # Check various possible data keys
                    for key in ['data', 'result', 'rows', 'items', 'records']:
                        if key in data and data[key]:
                            data_content = data[key]
                            print(f"✅ Found data in key: '{key}'")
                            break
                    
                    # If no data found in common keys, show what's available
                    if data_content is None:
                        print(f"❓ Available keys in response: {list(data.keys())}")
                        print(f"❓ Full response: {json.dumps(data, indent=2, ensure_ascii=False)}")
                        
                        # Try to find any non-empty values
                        for key, value in data.items():
                            if value and value != [] and value != {}:
                                print(f"🔍 Non-empty key '{key}': {str(value)[:200]}...")
                                data_content = value
                                break
                
                if data_content:
                    return self.parse_current_data(data_content, symbol)
                else:
                    print(f"❌ No current data available for symbol: {symbol}")
                    return None
                    
            except json.JSONDecodeError as e:
                print(f"❌ JSON parsing failed: {e}")
                print(f"📄 Response content: {raw_response}")
                return None
                
        except requests.RequestException as e:
            print(f"❌ Network error fetching current data for {symbol}: {e}")
            return None
        except Exception as e:
            print(f"❌ Error fetching current data for {symbol}: {e}")
            return None
    
    def fetch_historical_data(self, symbol: str, target_date: str) -> Optional[Dict]:
        """Fetch historical data from SZSE API"""
        ticker_padded = self.pad_ticker(symbol)
        
        params = {
            "SHOWTYPE": "JSON",
            "CATALOGID": "1394_stock_snapshot",
            "TABKEY": "tab1",
            "txtDMorJC": ticker_padded,
            "txtDate": target_date,
            "archiveDate": target_date,
            "random": "0.123456"
        }
        
        try:
            print(f"🔍 Fetching historical data for {symbol} ({ticker_padded}) on {target_date}")
            print(f"📡 API URL: {self.historical_url}")
            print(f"📋 Parameters: {params}")
            
            response = self.session.get(self.historical_url, params=params, timeout=10)
            response.raise_for_status()
            
            print(f"📄 Response Status: {response.status_code}")
            print(f"📄 Response Headers: {dict(response.headers)}")
            
            # Print raw response for debugging
            raw_response = response.text
            print(f"📄 Raw Response (first 500 chars): {raw_response[:500]}...")
            
            try:
                data = response.json()
                print(f"📊 Response type: {type(data)}")
                
                if isinstance(data, list):
                    print(f"📊 Response is array with {len(data)} elements")
                    for i, item in enumerate(data):
                        print(f"📊 Element {i}: {type(item)} - {list(item.keys()) if isinstance(item, dict) else str(item)[:100]}")
                elif isinstance(data, dict):
                    print(f"📊 Response is dict with keys: {list(data.keys())}")
                else:
                    print(f"📊 Response is {type(data)}: {str(data)[:200]}")
                
                # Handle different response structures
                data_content = None
                
                if isinstance(data, list):
                    # For array responses, look for data in elements after metadata
                    for i, item in enumerate(data):
                        if isinstance(item, dict):
                            # Skip metadata elements
                            if 'metadata' in item:
                                print(f"📊 Element {i}: Metadata (skipping)")
                                continue
                            # Look for data elements
                            elif 'data' in item or len(item) > 3:  # Assume non-metadata if has many fields
                                print(f"📊 Element {i}: Potential data element")
                                data_content = item.get('data', item)
                                break
                            # Also check if the item itself contains stock data fields
                            elif any(key in item for key in ['zqdm', 'stockcode', 'code', 'zqjc', 'stockname']):
                                print(f"📊 Element {i}: Direct stock data")
                                data_content = item
                                break
                    
                    # If no data found in individual elements, check if any element is a list of records
                    if data_content is None:
                        for i, item in enumerate(data):
                            if isinstance(item, dict) and 'data' in item and isinstance(item['data'], list):
                                print(f"📊 Element {i}: Contains data array")
                                data_content = item['data']
                                break
                
                elif isinstance(data, dict):
                    # Check various possible data keys
                    for key in ['data', 'result', 'rows', 'items', 'records']:
                        if key in data and data[key]:
                            data_content = data[key]
                            print(f"✅ Found data in key: '{key}'")
                            break
                    
                    # If no data found in common keys, show what's available
                    if data_content is None:
                        print(f"❓ Available keys in response: {list(data.keys())}")
                        print(f"❓ Full response: {json.dumps(data, indent=2, ensure_ascii=False)}")
                        
                        # Try to find any non-empty values
                        for key, value in data.items():
                            if value and value != [] and value != {}:
                                print(f"🔍 Non-empty key '{key}': {str(value)[:200]}...")
                                data_content = value
                                break
                
                # Final fallback - if we have an array and no specific data found, try the array itself
                if data_content is None and isinstance(data, list) and len(data) > 1:
                    print("🔍 Trying to use array elements directly as data...")
                    # Skip metadata element and use remaining
                    for item in data[1:]:
                        if isinstance(item, dict) and len(item) > 1:
                            data_content = item
                            print(f"🔍 Using element as data: {list(item.keys())}")
                            break
                
                if data_content:
                    print(f"✅ Found data content: {type(data_content)}")
                    return self.parse_historical_data(data_content, symbol, target_date)
                else:
                    print(f"❌ No data content found for symbol: {symbol} on {target_date}")
                    print(f"📄 Full response structure: {json.dumps(data, indent=2, ensure_ascii=False)}")
                    return None
                    
            except json.JSONDecodeError as e:
                print(f"❌ JSON parsing failed: {e}")
                print(f"📄 Response content: {raw_response}")
                return None
                
        except requests.RequestException as e:
            print(f"❌ Network error fetching historical data for {symbol}: {e}")
            return None
        except Exception as e:
            print(f"❌ Error fetching historical data for {symbol}: {e}")
            return None
    
    def parse_current_data(self, api_data: Dict, symbol: str) -> Dict:
        """Parse current data from SZSE API response"""
        try:
            # Adapt this based on actual SZSE current data API response structure
            # Common fields that might be available:
            stock_data = {
                'symbol': symbol,
                'name': api_data.get('stockname', api_data.get('name', 'N/A')),
                'open': float(api_data.get('open', api_data.get('openPrice', 0))),
                'data_type': 'current'
            }
            
            return stock_data
            
        except Exception as e:
            print(f"Error parsing current data for {symbol}: {e}")
            return None
    
    def parse_historical_data(self, api_data: any, symbol: str, target_date: str) -> Dict:
        """Parse historical data from SZSE API response"""
        try:
            print(f"🔧 Parsing historical data for {symbol}")
            print(f"🔧 Data type: {type(api_data)}")
            
            # Handle different data structures
            data_record = None
            
            if isinstance(api_data, list):
                print(f"🔧 Data is a list with {len(api_data)} items")
                if len(api_data) > 0:
                    data_record = api_data[0]
                    print(f"🔧 Using first record: {list(data_record.keys()) if isinstance(data_record, dict) else str(data_record)[:100]}")
                else:
                    print("❌ Empty list returned")
                    return None
            elif isinstance(api_data, dict):
                print(f"🔧 Data is a dict with keys: {list(api_data.keys())}")
                data_record = api_data
            else:
                print(f"❌ Unexpected data type: {type(api_data)}")
                return None
            
            if not data_record:
                print("❌ No data record to parse")
                return None
                
            print(f"🔧 Record keys: {list(data_record.keys()) if isinstance(data_record, dict) else 'Not a dict'}")
            
            # Try different field mappings for SZSE API
            field_mappings = {
                'name': ['zqjc', 'stockname', 'name', 'gsjc', 'mc'],
                'open': ['ks', 'kpjg', 'open', 'kaiPanJia'],  # ks = 开盘 (open)
            }
            
            def safe_float_conversion(value, default=0):
                """Safely convert string to float, handling commas and empty values"""
                if value is None or value == '' or value == '-':
                    return default
                
                # Convert to string and remove commas
                str_value = str(value).replace(',', '').strip()
                
                try:
                    return float(str_value)
                except (ValueError, TypeError):
                    print(f"⚠️ Could not convert '{value}' to float, using default {default}")
                    return default
            
            def get_field_value(field_names: list, default=0, is_numeric=True):
                """Try to get value from multiple possible field names"""
                for field_name in field_names:
                    if field_name in data_record and data_record[field_name] is not None:
                        value = data_record[field_name]
                        if isinstance(value, str) and value.strip() == '':
                            continue
                        print(f"🔧 Found {field_names[0]} in field '{field_name}': {value}")
                        
                        if is_numeric:
                            return safe_float_conversion(value, default)
                        else:
                            return value
                print(f"⚠️ Could not find {field_names[0]} in any of: {field_names}")
                return default
            
            # Extract only essential data
            stock_data = {
                'symbol': symbol,
                'name': get_field_value(field_mappings['name'], 'N/A', is_numeric=False),
                'open': get_field_value(field_mappings['open'], 0),
                'data_type': 'historical'
            }
            
            print(f"✅ Successfully parsed data for {symbol}:")
            print(f"   📊 Name: {stock_data['name']}")
            print(f"   💰 Open: ¥{stock_data['open']:.2f}")
            
            return stock_data
            
        except Exception as e:
            print(f"❌ Error parsing historical data for {symbol}: {e}")
            if 'data_record' in locals():
                print(f"❌ Data record keys: {list(data_record.keys()) if isinstance(data_record, dict) else 'Not a dict'}")
                print(f"❌ Data record content: {data_record}")
            return None
    
    def get_stock_data(self, symbol: str, expected_open: float = None, target_date: str = None) -> Optional[Dict]:
        """
        Fetch stock data (current or historical) from SZSE API
        target_date: YYYY-MM-DD format, if None gets current data
        expected_open: Expected open price for comparison
        """
        mode, date_str = self.get_date_mode(target_date)
        
        if mode == "invalid":
            print(f"⚠ Date {target_date} is in the future — skipping.")
            return None
        
        # Handle market closed scenarios
        if mode == "market_closed_weekend":
            print(f"📅 {date_str} is a weekend — Market Closed")
            return self.create_market_closed_result(symbol, expected_open, "Weekend - Market Closed")
        
        if mode == "market_closed_now":
            print(f"🕐 Market is currently closed")
            return self.create_market_closed_result(symbol, expected_open, "Outside Trading Hours")
        
        # Fetch data based on mode
        if mode == "current":
            stock_data = self.fetch_current_data(symbol)
        else:  # historical
            stock_data = self.fetch_historical_data(symbol, date_str)
        
        if stock_data is None:
            return None
        
        # Add expected data and matching logic
        stock_data['expected_open'] = expected_open
        
        # Add matching status
        if expected_open is not None:
            tolerance = 0.01  # 1 cent tolerance
            if abs(stock_data['open'] - expected_open) <= tolerance:
                stock_data['match_status'] = 'MATCHED'
            else:
                stock_data['match_status'] = 'NOT MATCHED'
        else:
            stock_data['match_status'] = 'NO EXPECTED PRICE'
        
        return stock_data
    
    def get_multiple_symbols(self, symbols_data: List[Dict], target_date: str = None) -> List[Dict]:
        """
        Fetch data for multiple symbols with expected data
        symbols_data: List of dicts with 'symbol' and 'expected_open' keys
        target_date: YYYY-MM-DD format, if None gets current data
        """
        results = []
        for symbol_info in symbols_data:
            symbol = symbol_info['symbol']
            expected_open = symbol_info['expected_open']
            
            data = self.get_stock_data(symbol, expected_open, target_date)
            if data:
                results.append(data)
            time.sleep(0.5)  # Slightly longer delay for official API
        return results
    
    def display_simple_result(self, data: Dict):
        """Display simplified result"""
        if data['match_status'] == 'MARKET CLOSED':
            status_emoji = "🔒"
            open_price_display = "Market Closed"
            print(f"{status_emoji} {data['symbol']} | {data['data_type']} | Expected: ¥{data['expected_open']:.2f} | Status: {open_price_display}")
        else:
            data_type = "Current" if data['data_type'] == 'current' else "Historical"
            status_emoji = "✅" if data['match_status'] == 'MATCHED' else "❌"
            print(f"{status_emoji} {data['symbol']} | {data_type} Open: ¥{data['open']:.2f} | Expected: ¥{data['expected_open']:.2f} | Status: {data['match_status']}")
    
    def display_simple_summary(self, data_list: List[Dict]):
        """Display simplified summary table"""
        if not data_list:
            print("No data to display.")
            return
        
        print(f"\n{'='*80}")
        print("PRICE MATCH RESULTS")
        print(f"{'='*80}")
        
        # Create formatted table
        header = f"{'Symbol':<8} {'Type':<18} {'Actual Open':<12} {'Expected Open':<14} {'Status':<12}"
        print(header)
        print("-" * len(header))
        
        matched_count = 0
        market_closed_count = 0
        for data in data_list:
            if data['match_status'] == 'MARKET CLOSED':
                data_type = data['data_type']
                status_emoji = "🔒"
                open_display = "Market Closed"
                
                row = (f"{data['symbol']:<8} "
                       f"{data_type:<18} "
                       f"{open_display:<12} "
                       f"¥{data['expected_open']:<13.2f} "
                       f"{status_emoji} MARKET CLOSED")
                print(row)
                market_closed_count += 1
            else:
                data_type = "Current" if data['data_type'] == 'current' else "Historical"
                status_emoji = "✅" if data['match_status'] == 'MATCHED' else "❌"
                
                row = (f"{data['symbol']:<8} "
                       f"{data_type:<18} "
                       f"¥{data['open']:<11.2f} "
                       f"¥{data['expected_open']:<13.2f} "
                       f"{status_emoji} {data['match_status']:<8}")
                print(row)
                
                if data['match_status'] == 'MATCHED':
                    matched_count += 1
        
        print("-" * len(header))
        tradeable_count = len(data_list) - market_closed_count
        if tradeable_count > 0:
            print(f"📊 Price Matches: {matched_count}/{tradeable_count} tradeable symbols matched expected prices")
        if market_closed_count > 0:
            print(f"🔒 Market Closed: {market_closed_count} symbol(s) on non-trading time/date")
        print(f"{'='*80}")

def get_symbols_with_expected_prices():
    """Get symbols with expected open prices from user (simplified)"""
    print("="*60)
    print("Enter stock data (Symbol, Expected Open Price)")
    print("="*60)
    
    symbols_data = []
    
    while True:
        print(f"\nEntering stock #{len(symbols_data) + 1}:")
        print("(Press Enter on Symbol to finish)")
        
        # Get Symbol
        symbol = input("Enter Symbol (e.g., 300928): ").strip()
        if not symbol:
            break
            
        if not (symbol.isdigit() and len(symbol) == 6):
            print("Invalid symbol format. Please enter a 6-digit stock code.")
            continue
        
        # Get Expected Open Price
        while True:
            try:
                equ_price_input = input("Enter Expected Open Price: ").strip()
                if not equ_price_input:
                    print("Please enter a valid price.")
                    continue
                equ_price = float(equ_price_input)
                break
            except ValueError:
                print("Invalid price format. Please enter a number (e.g., 34.11).")
        
        symbols_data.append({
            'symbol': symbol,
            'expected_open': equ_price
        })
        
        print(f"✅ Added: {symbol} - ¥{equ_price:.2f}")
        
        # Ask if user wants to add more
        continue_choice = input("\nAdd another stock? (y/n, default is y): ").strip().lower()
        if continue_choice in ['n', 'no']:
            break
    
    return symbols_data

def get_target_date():
    """Get target date from user"""
    print("\n" + "="*40)
    print("Data Date Selection:")
    print("1. Current/Real-time data")
    print("2. Historical data (specific date)")
    print("="*40)
    print("📝 Note: Market is closed on weekends")
    print("🕐 Trading hours: 9:30-11:30, 13:00-15:00 (Beijing time)")
    
    choice = input("Enter your choice (1-2, default is 1): ").strip()
    
    if choice == '2':
        while True:
            date_input = input("Enter date (YYYY-MM-DD): ").strip()
            try:
                # Validate date format
                date_obj = datetime.strptime(date_input, '%Y-%m-%d')
                
                # Check if it's a weekend
                if date_obj.weekday() >= 5:  # Saturday = 5, Sunday = 6
                    weekend_day = "Saturday" if date_obj.weekday() == 5 else "Sunday"
                    print(f"⚠️ {date_input} is a {weekend_day} - Market will be closed")
                    confirm = input("Continue with this date? (y/n): ").strip().lower()
                    if confirm not in ['y', 'yes']:
                        continue
                
                return date_input
            except ValueError:
                print("Invalid date format. Please use YYYY-MM-DD format.")
    else:
        return None  # Current data

def show_menu():
    """Display main menu options"""
    print("\n" + "="*50)
    print("🏛️ SZSE Stock Price Matcher 🏛️")
    print("="*50)
    print("Choose an option:")
    print("1. Check stock prices vs expected prices")
    print("2. Test single symbol")
    print("3. Exit")
    print("="*50)

def main():
    """Main interactive function"""
    print("🔥 SZSE Stock Price Matcher 🔥")
    print("Compare actual opening prices with your expected prices!")
    
    fetcher = SZSEOfficialDataFetcher()
    
    while True:
        show_menu()
        choice = input("Enter your choice (1-3): ").strip()
        
        if choice == '1':
            # Get target date
            target_date = get_target_date()
            
            # Get symbols with expected prices
            symbols_data = get_symbols_with_expected_prices()
            
            if not symbols_data:
                print("No stocks entered. Returning to main menu.")
                continue
            
            symbols = [data['symbol'] for data in symbols_data]
            date_info = f" for {target_date}" if target_date else " (current/real-time)"
            print(f"\nFetching data from SZSE API{date_info}")
            print(f"Symbols: {', '.join(symbols)}")
            print("Please wait...")
            
            # Fetch data
            all_data = fetcher.get_multiple_symbols(symbols_data, target_date)
            
            if all_data:
                print(f"\n✅ Successfully fetched data for {len(all_data)} symbol(s)")
                
                # Display simplified results
                fetcher.display_simple_summary(all_data)
                
            else:
                print("❌ No data retrieved. Please check your symbols and try again.")
            
            # Ask if user wants to continue
            continue_choice = input("\nWould you like to check more stocks? (y/n): ").strip().lower()
            if continue_choice not in ['y', 'yes']:
                break
        
        elif choice == '2':
            # Test single symbol
            print("\n🔧 Single Symbol Test")
            print("=" * 50)
            
            symbol = input("Enter 6-digit symbol (e.g., 301055): ").strip()
            if not symbol.isdigit() or len(symbol) != 6:
                print("❌ Invalid symbol format. Please enter a 6-digit number.")
                continue
            
            # Get expected open price
            while True:
                try:
                    expected_open_str = input("Enter Expected Open Price: ").strip()
                    if expected_open_str:
                        expected_open = float(expected_open_str)
                        break
                    else:
                        expected_open = None
                        break
                except ValueError:
                    print("❌ Invalid price format. Please enter a number (e.g., 19.73).")
            
            target_date = get_target_date()
            
            print(f"\n🚀 Testing symbol {symbol}...")
            if expected_open is not None:
                print(f"💰 Expected Open Price: ¥{expected_open:.2f}")
            if target_date:
                print(f"📅 Target date: {target_date}")
            else:
                print("📈 Mode: Current/Real-time")
            
            print(f"\n" + "="*60)
            print("🔍 API CALL:")
            print("="*60)
            
            # Test the API call
            data = fetcher.get_stock_data(symbol, expected_open, target_date)
            
            if data:
                print(f"\n" + "="*60)
                print("✅ RESULT:")
                print("="*60)
                
                fetcher.display_simple_result(data)
                
            else:
                print(f"\n❌ FAILED to retrieve data for {symbol}")
                
        elif choice == '3':
            print("Thank you for using the SZSE Stock Price Matcher! 👋")
            break
        else:
            print("Invalid choice. Please enter 1, 2, or 3.")

# Quick function for single symbol lookup
def quick_lookup(symbol: str, expected_open: float = None, target_date: str = None):
    """Quick lookup for a single symbol with expected price"""
    fetcher = SZSEOfficialDataFetcher()
    
    data = fetcher.get_stock_data(symbol, expected_open, target_date)
    if data:
        fetcher.display_simple_result(data)
        return data
    else:
        print(f"No data found for symbol: {symbol}")
        return None

if __name__ == "__main__":
    main()