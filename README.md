## Overview

This project implements a **volatility and inventory-aware market making strategy** on **Binance Futures Testnet** using [Hummingbot](https://hummingbot.org/). The strategy dynamically adjusts bid/ask spreads based on **NATR (Normalized Average True Range)**, **RSI (Relative Strength Index)**, and **inventory balance**, aiming to improve execution quality and inventory management.

The system continuously fetches ETH/USDT 1-minute candles via **CCXT**, calculates indicators in real time, and places/cancels limit orders accordingly.

---

## ✨ Features

* **Dynamic Spread Control**

  * Adjusts bid/ask spreads using volatility (NATR).
* **Inventory-Aware Adjustments**

  * Shifts reference price based on current ETH/USDT balance.
* **RSI-Based Price Shifts**

  * Adapts spreads based on market momentum.
* **Automated Candle Updates**

  * Background thread fetches OHLCV candles every 10s.
* **Market-Making Loop**

  * Places/cancels limit orders with refresh intervals.
* **Debugging & Monitoring**

  * Logs balances, active orders, spreads, RSI values, and recent candles.

---

## ⚙️ Requirements

* Python 3.8+
* [Hummingbot](https://hummingbot.org/)
* [CCXT](https://github.com/ccxt/ccxt)
* pandas, numpy

Install dependencies:

```bash
pip install hummingbot ccxt pandas numpy
```

---

## 🚀 Usage

1. Clone the repository and move the strategy script:

   ```bash
   git clone <your-repo-url>
   cd <your-repo>
   ```

2. Place `quant_strategy.py` in your Hummingbot `scripts/` directory.

3. Start Hummingbot and load the script:

   ```bash
   bin/hummingbot
   config script quant_strategy.py
   start
   ```

---

## 📊 Key Parameters

* `NATR_PERIOD = 30` → Window size for volatility.
* `RSI_PERIOD = 30` → RSI lookback period.
* `BID_SPREAD_MULTIPLIER = 120` → Multiplier for bid spread.
* `ASK_SPREAD_MULTIPLIER = 60` → Multiplier for ask spread.
* `ORDER_REFRESH_TIME = 15s` → Order update frequency.
* `ORDER_AMOUNT = 0.01` ETH.

---

## 📝 Status Reporting

The strategy prints:

* Balances (ETH & USDT).
* Active orders.
* Spreads, RSI, and inventory shifts.
* Recent candles (last 3).

---

## 🔍 Example Log Output

```
Balances -> ETH: 0.500000, USDT: 1000.00
Bid Spread: 0.4500%, Ask Spread: 0.2500%
RSI: 52.34 | RSI Shift: -0.00000045 | Inventory Shift: 0.00000001
Recent Candles:
  2025-09-01 14:10:00 O:2000.00 H:2010.00 L:1995.00 C:2005.00
```
