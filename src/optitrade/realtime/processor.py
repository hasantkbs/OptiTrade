import asyncio
from typing import Dict, Callable
import pandas as pd

MAX_HISTORY_SIZE = 1000 # Maximum number of klines to store for each symbol-interval pair

class Processor:
    def __init__(self):
        self.model_pipelines: Dict[str, Dict[str, Callable]] = {
            "short_term": {},
            "long_term": {}
        } # {analysis_type: {interval: model_pipeline_func}}
        self.kline_history: Dict[tuple, pd.DataFrame] = {} # Stores DataFrame for (symbol, interval)

    def register_model_pipeline(self, analysis_type: str, interval: str, pipeline_func: Callable):
        """Registers a model pipeline function for a specific analysis type and interval."""
        if analysis_type not in self.model_pipelines:
            self.model_pipelines[analysis_type] = {}
        self.model_pipelines[analysis_type][interval] = pipeline_func
        print(f"Registered model pipeline for {analysis_type} - {interval}")

    async def process_kline_data(self, kline_data: dict):
        """Processes incoming kline data, updates history, and dispatches it to registered model pipelines."""
        symbol = kline_data['symbol']
        interval = kline_data['interval']
        
        # Update kline history
        new_kline_df = pd.DataFrame([kline_data], index=[pd.to_datetime(kline_data['close_time'], unit='ms')])
        new_kline_df.index.name = 'timestamp'
        
        history_key = (symbol, interval)
        if history_key not in self.kline_history:
            self.kline_history[history_key] = pd.DataFrame(columns=['symbol', 'interval', 'open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume'])
        
        # Append new kline and trim history
        self.kline_history[history_key] = pd.concat([self.kline_history[history_key], new_kline_df])
        self.kline_history[history_key] = self.kline_history[history_key].tail(MAX_HISTORY_SIZE)

        # Determine analysis type based on interval
        analysis_type = None
        if interval in ['1m', '15m']:
            analysis_type = "short_term"
        elif interval in ['4h', '1w', '1M']:
            analysis_type = "long_term"
        
        # 4h can be used for both, so we need to handle it specifically
        if interval == '4h':
            # Dispatch to both short_term and long_term if pipelines exist
            if "short_term" in self.model_pipelines and interval in self.model_pipelines["short_term"]:
                print(f"Dispatching 4h kline to short_term pipeline for {symbol}")
                await self.model_pipelines["short_term"][interval](self.kline_history[history_key])
            if "long_term" in self.model_pipelines and interval in self.model_pipelines["long_term"]:
                print(f"Dispatching 4h kline to long_term pipeline for {symbol}")
                await self.model_pipelines["long_term"][interval](self.kline_history[history_key])
            return # Handled 4h, so return

        if analysis_type and analysis_type in self.model_pipelines and interval in self.model_pipelines[analysis_type]:
            print(f"Dispatching {interval} kline to {analysis_type} pipeline for {symbol}")
            await self.model_pipelines[analysis_type][interval](self.kline_history[history_key])
        else:
            print(f"No registered pipeline for {analysis_type} - {interval} for {symbol}")

if __name__ == '__main__':
    async def dummy_short_term_pipeline(data):
        print(f"Short-term pipeline received: {data['symbol']} {data['interval']} - Close: {data['close']}")

    async def dummy_long_term_pipeline(data):
        print(f"Long-term pipeline received: {data['symbol']} {data['interval']} - Close: {data['close']}")

    async def main():
        processor = Processor()
        processor.register_model_pipeline("short_term", "1m", dummy_short_term_pipeline)
        processor.register_model_pipeline("short_term", "15m", dummy_short_term_pipeline)
        processor.register_model_pipeline("short_term", "4h", dummy_short_term_pipeline)
        processor.register_model_pipeline("long_term", "4h", dummy_long_term_pipeline)
        processor.register_model_pipeline("long_term", "1w", dummy_long_term_pipeline)
        processor.register_model_pipeline("long_term", "1M", dummy_long_term_pipeline)

        # Simulate incoming kline data
        await processor.process_kline_data({'symbol': 'BTCUSDT', 'interval': '1m', 'close': 30000.0})
        await processor.process_kline_data({'symbol': 'BTCUSDT', 'interval': '15m', 'close': 30100.0})
        await processor.process_kline_data({'symbol': 'BTCUSDT', 'interval': '4h', 'close': 30500.0})
        await processor.process_kline_data({'symbol': 'BTCUSDT', 'interval': '1w', 'close': 31000.0})
        await processor.process_kline_data({'symbol': 'BTCUSDT', 'interval': '1M', 'close': 32000.0})
        await processor.process_kline_data({'symbol': 'ETHUSDT', 'interval': '1m', 'close': 2000.0})

    asyncio.run(main())
