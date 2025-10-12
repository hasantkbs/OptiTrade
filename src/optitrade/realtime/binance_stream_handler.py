import asyncio
from binance import AsyncClient, BinanceSocketManager

class BinanceStreamHandler:
    def __init__(self, api_key: str, api_secret: str, symbols: list, intervals: list):
        self.api_key = api_key
        self.api_secret = api_secret
        self.symbols = symbols
        self.intervals = intervals
        self.client = None
        self.bsm = None
        self.callbacks = {} # {interval: [callback_func]}

    async def _start_client(self):
        if not self.client:
            self.client = await AsyncClient.create(self.api_key, self.api_secret)
            self.bsm = BinanceSocketManager(self.client)

    async def _process_kline_message(self, msg):
        """Processes incoming kline messages and calls registered callbacks."""
        if msg['e'] == 'kline':
            kline = msg['k']
            symbol = kline['s']
            interval = kline['i']
            is_final = kline['x'] # True if kline is closed

            if is_final: # Only process closed candles for analysis
                # Construct a clean kline dictionary
                processed_kline = {
                    'symbol': symbol,
                    'interval': interval,
                    'open_time': kline['t'],
                    'open': float(kline['o']),
                    'high': float(kline['h']),
                    'low': float(kline['l']),
                    'close': float(kline['c']),
                    'volume': float(kline['v']),
                    'close_time': kline['T'],
                    'quote_asset_volume': float(kline['q']),
                    'number_of_trades': kline['n'],
                    'taker_buy_base_asset_volume': float(kline['V']),
                    'taker_buy_quote_asset_volume': float(kline['Q']),
                }
                # Call all registered callbacks for this interval
                if interval in self.callbacks:
                    for callback in self.callbacks[interval]:
                        await callback(processed_kline)

    def register_kline_callback(self, interval: str, callback_func):
        """Registers a callback function to be called when a kline for the given interval is closed."""
        if interval not in self.callbacks:
            self.callbacks[interval] = []
        self.callbacks[interval].append(callback_func)
        print(f"Registered callback for interval: {interval}")

    async def start_kline_streams(self):
        """Starts kline WebSocket streams for all symbols and intervals."""
        await self._start_client()
        if not self.bsm:
            print("Binance Socket Manager not initialized.")
            return

        print(f"Starting kline streams for symbols: {self.symbols} and intervals: {self.intervals}")
        
        # Create a list of futures for all kline streams
        streams = []
        for symbol in self.symbols:
            for interval in self.intervals:
                # Binance API expects lowercase for stream names
                stream_name = f"{symbol.lower()}@kline_{interval}"
                streams.append(self.bsm.kline_socket(symbol=symbol, interval=interval))
        
        # Start all streams concurrently
        self.conn_keys = []
        for stream in streams:
            conn_key = await stream.__aenter__() # Enter the async context manager
            self.conn_keys.append(conn_key)
            asyncio.create_task(self._listen_stream(conn_key)) # Listen to each stream in a separate task

        print("All kline streams started.")

    async def _listen_stream(self, conn_key):
        """Listens to a single stream and processes messages."""
        while True:
            try:
                msg = await conn_key.recv()
                await self._process_kline_message(msg)
            except Exception as e:
                print(f"Error in stream listener: {e}")
                # Implement re-connection logic here if needed
                break # Exit loop on error for now

    async def stop_kline_streams(self):
        """Stops all active kline WebSocket streams."""
        if self.bsm and self.conn_keys:
            for conn_key in self.conn_keys:
                await conn_key.__aexit__(None, None, None) # Exit the async context manager
            print("All kline streams stopped.")
        if self.client:
            await self.client.close_connection()
            print("Binance client connection closed.")

if __name__ == '__main__':
    # This is an example of how to use the BinanceStreamHandler
    # Replace with your actual API key and secret
    API_KEY = "YOUR_API_KEY"
    API_SECRET = "YOUR_API_SECRET"

    # For testing, use a testnet or ensure you have proper error handling
    # and rate limit management for production keys.

    async def my_callback(kline_data):
        print(f"Received kline: {kline_data['symbol']} {kline_data['interval']} - Close: {kline_data['close']}")

    async def main():
        # Example usage: BTCUSDT for 1m and 15m intervals
        symbols_to_stream = ['BTCUSDT']
        intervals_to_stream = ['1m', '15m']

        handler = BinanceStreamHandler(API_KEY, API_SECRET, symbols_to_stream, intervals_to_stream)
        handler.register_kline_callback('1m', my_callback)
        handler.register_kline_callback('15m', my_callback)

        try:
            await handler.start_kline_streams()
            # Keep the main task running to allow streams to operate
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("Stopping streams...")
        finally:
            await handler.stop_kline_streams()

    # To run this example, you need to install python-binance: pip install python-binance
    # And replace YOUR_API_KEY and YOUR_API_SECRET with actual credentials.
    # For a real application, manage API keys securely (e.g., environment variables).
    asyncio.run(main())
