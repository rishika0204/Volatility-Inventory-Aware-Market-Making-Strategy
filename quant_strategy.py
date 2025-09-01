from typing import TYPE_CHECKING, Dict
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase
from hummingbot.core.event.events import OrderType, PositionAction, BuyOrderCreatedEvent, SellOrderCreatedEvent
import pandas as pd
import numpy as np
import time
from decimal import Decimal, InvalidOperation
import threading
import ccxt

if TYPE_CHECKING:
    from hummingbot.connector.connector_base import ConnectorBase

class VolatilityInventoryMarketMakingStrategy(ScriptStrategyBase):
    markets = {"binance_perpetual_testnet": {"ETH-USDT"}}

    NATR_PERIOD = 30
    RSI_PERIOD = 30
    BID_SPREAD_MULTIPLIER = 120
    ASK_SPREAD_MULTIPLIER = 60
    RSI_THRESHOLD = 50
    RSI_SHIFT_MAX = 0.000001
    RSI_SHIFT_SCALAR = -1
    TARGET_BASE_RATIO = 0.5
    INV_SHIFT_MAX = 0.000001
    ORDER_AMOUNT = 0.01
    ORDER_REFRESH_TIME = 15  # seconds

    def __init__(self, connectors: Dict[str, "ConnectorBase"]):
        super().__init__(connectors)
        self.bid_order_id = None
        self.ask_order_id = None
        self._last_update = 0.0

        self.candles_df = None
        self._start_candle_updater()

        self.last_mid_price = None
        self.last_ref_price = None
        self.last_natr = None
        self.last_rsi = None
        self.last_price_shift_rsi = None
        self.last_price_shift_inv = None
        self.last_bid_spread = None
        self.last_ask_spread = None
        self.last_bid_price = None
        self.last_ask_price = None

    def _start_candle_updater(self):
        # Start a background thread to update self.candles_df every 10 seconds
        def update_candles():
            exchange = ccxt.binance({"options": {"defaultType": "future"}})
            exchange.set_sandbox_mode(True)  # Testnet mode
            while True:
                try:
                    bars = exchange.fetch_ohlcv("ETH/USDT", timeframe="1m", limit=50)
                    self.candles_df = pd.DataFrame(bars, columns=["timestamp", "open", "high", "low", "close", "volume"])
                except Exception as e:
                    self.logger().error(f"Error fetching candles: {e}")
                time.sleep(10)
        t = threading.Thread(target=update_candles, daemon=True)
        t.start()

    def on_tick(self):
        if not self.ready_to_trade:
            return

        now = time.time()
        if now - self._last_update < self.ORDER_REFRESH_TIME:
            return
        self._last_update = now

        candles_df = self.candles_df
        if candles_df is None or len(candles_df) < max(self.NATR_PERIOD, self.RSI_PERIOD):
            self.logger().info("Waiting for sufficient candle data...")
            return

        # -- Usual calculations (unchanged) --
        try:
            mid_price = self.connectors["binance_perpetual_testnet"].get_mid_price("ETH-USDT")
            if mid_price is None:
                self.logger().warning("Mid price not available.")
                return
            mid_price = float(mid_price)
        except Exception as e:
            self.logger().error(f"Failed to get mid price: {e}")
            return

        try:
            highs = candles_df["high"].astype(float).values
            lows = candles_df["low"].astype(float).values
            closes = candles_df["close"].astype(float).values
            prev_close = np.roll(closes, 1)
            true_range = np.maximum(highs - lows,
                                    np.maximum(np.abs(highs - prev_close), np.abs(lows - prev_close)))
            atr = np.mean(true_range[-self.NATR_PERIOD:])
            natr = atr / mid_price if mid_price > 0 else 0.0
        except Exception as e:
            self.logger().error(f"ATR/NATR calculation error: {e}")
            return

        try:
            deltas = np.diff(closes)
            ups = np.where(deltas > 0, deltas, 0.0)
            downs = np.where(deltas < 0, -deltas, 0.0)
            avg_gain = np.mean(ups[-self.RSI_PERIOD:]) if len(ups) >= self.RSI_PERIOD else np.mean(ups) if len(ups) else 0.0
            avg_loss = np.mean(downs[-self.RSI_PERIOD:]) if len(downs) >= self.RSI_PERIOD else np.mean(downs) if len(downs) else 0.0
            rs = avg_gain / avg_loss if avg_loss != 0 else np.inf
            rsi = 100 - (100 / (1 + rs)) if avg_loss != 0 else 100.0
        except Exception as e:
            self.logger().error(f"RSI calculation error: {e}")
            return

        try:
            rsi_adj = (rsi - self.RSI_THRESHOLD) / self.RSI_THRESHOLD
            price_shift_rsi = rsi_adj * self.RSI_SHIFT_MAX * self.RSI_SHIFT_SCALAR

            connector = self.connectors["binance_perpetual_testnet"]
            base_balance = float(connector.get_balance("ETH") or 0)
            quote_balance = float(connector.get_balance("USDT") or 0)
            base_value = base_balance * mid_price
            total_value = base_value + quote_balance
            inv_ratio = base_value / total_value if total_value > 0 else self.TARGET_BASE_RATIO
            price_shift_inv = (inv_ratio - self.TARGET_BASE_RATIO) * self.INV_SHIFT_MAX

            ref_price = mid_price * (1 + price_shift_rsi + price_shift_inv)
            bid_spread = natr * self.BID_SPREAD_MULTIPLIER
            ask_spread = natr * self.ASK_SPREAD_MULTIPLIER

            bid_price = mid_price * 1.01
            ask_price = mid_price * 0.99

            self.last_mid_price = mid_price
            self.last_ref_price = ref_price
            self.last_natr = natr
            self.last_rsi = rsi
            self.last_price_shift_rsi = price_shift_rsi
            self.last_price_shift_inv = price_shift_inv
            self.last_bid_spread = bid_spread
            self.last_ask_spread = ask_spread
            self.last_bid_price = bid_price
            self.last_ask_price = ask_price
        except Exception as e:
            self.logger().error(f"Spread/price calculation error: {e}")
            return

        # ---- MARKET ORDER TEST SECTION ----
        if not hasattr(self, "has_bought"):
            self.has_bought = False

        if not self.has_bought:
            try:
                dec_amount = Decimal(str(self.ORDER_AMOUNT))
                self.logger().info("Placing one-time MARKET BUY for testing.")
                self.buy(
                    "binance_perpetual_testnet",
                    "ETH-USDT",
                    dec_amount,
                    OrderType.MARKET,
                    None,
                    PositionAction.OPEN,
                )
                self.has_bought = True
            except (InvalidOperation, Exception) as e:
                self.logger().error(f"Error placing market buy: price and amount must be Decimal objects. Details: {e}")

        # ---- END MARKET ORDER TEST ----

        try:
            if self.bid_order_id:
                self.cancel("binance_perpetual_testnet", "ETH-USDT", self.bid_order_id)
            if self.ask_order_id:
                self.cancel("binance_perpetual_testnet", "ETH-USDT", self.ask_order_id)
        except Exception as e:
            self.logger().error(f"Error cancelling orders: {e}")

        try:
            dec_bid_price = Decimal(str(bid_price))
            dec_ask_price = Decimal(str(ask_price))
            dec_amount = Decimal(str(self.ORDER_AMOUNT))

            self.buy("binance_perpetual_testnet", "ETH-USDT", dec_amount,
                    OrderType.LIMIT, dec_bid_price, PositionAction.OPEN)
            self.sell("binance_perpetual_testnet", "ETH-USDT", dec_amount,
                    OrderType.LIMIT, dec_ask_price, PositionAction.OPEN)
        except (InvalidOperation, Exception) as e:
            self.logger().error(f"Error placing orders: price and amount must be Decimal objects. Details: {e}")

    def did_create_buy_order(self, event: BuyOrderCreatedEvent):
        self.bid_order_id = event.order_id

    def did_create_sell_order(self, event: SellOrderCreatedEvent):
        self.ask_order_id = event.order_id

    def format_status(self) -> str:
        if not self.ready_to_trade:
            return "Market connectors are not ready."

        lines = []
        try:
            connector = self.connectors["binance_perpetual_testnet"]
            base_bal = float(connector.get_balance("ETH") or 0)
            quote_bal = float(connector.get_balance("USDT") or 0)
            lines.append(f"Balances -> ETH: {base_bal:.6f}, USDT: {quote_bal:.2f}")
            # Perp position reporting: dictionary of trading_pair -> Position object
            try:
                positions = connector.account_positions
                lines.append(f"DEBUG: Raw positions: {positions}")
                for trading_pair, position in positions.items():
                    # If your Position object is a namedtuple or similar:
                    try:
                        lines.append(
                            f"Perp Position -> {trading_pair}: {getattr(position, 'amount', '?')} ETH at entry price {getattr(position, 'entry_price', '?')}"
                        )
                    except Exception as ee:
                        lines.append(f"DEBUG: Could not parse position {trading_pair}: {ee}")
            except Exception as e:
                lines.append(f"Could not fetch positions: {e}")
        except Exception:
            lines.append("Balances not available")


        try:
            orders_df = self.active_orders_df()
            if orders_df is not None and not orders_df.empty:
                lines.append("Active Orders:")
                lines.extend(orders_df.to_string(index=False).splitlines())
        except ValueError:
            # No active orders, don't add anything
            pass

        if self.last_ref_price is not None:
            lines.append(f"Bid Spread: {self.last_bid_spread*100:.4f}%, Ask Spread: {self.last_ask_spread*100:.4f}%")
        if self.last_rsi is not None:
            lines.append(f"RSI: {self.last_rsi:.2f} | RSI Shift: {self.last_price_shift_rsi:.8f} | Inventory Shift: {self.last_price_shift_inv:.8f}")

        candles_df = self.candles_df
        if candles_df is not None and len(candles_df) >= 3:
            recent = candles_df[["timestamp","open","high","low","close"]].tail(3)
            lines.append("Recent Candles (last 3):")
            for _, row in recent.iterrows():
                ts = pd.to_datetime(row["timestamp"], unit="ms").strftime('%Y-%m-%d %H:%M:%S')
                lines.append(
                    f"  {ts} O:{row['open']:.4f} H:{row['high']:.4f} "
                    f"L:{row['low']:.4f} C:{row['close']:.4f}"
                )
        return "\n".join(lines)
