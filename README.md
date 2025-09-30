# 🚀 Crypto Tracker with Modern UI

A **real-time cryptocurrency tracker** built with **Python, PySide6, matplotlib, and mplfinance**.
This app features a modern UI with dark/light themes, candlestick charts, table & card views, and non-blocking data fetching from the [CoinGecko API](https://www.coingecko.com/).

---

## ✨ Features

* 📊 **Live crypto prices & market data** (via CoinGecko API)
* 🕒 **Auto-refresh** with custom intervals (30s, 1m, 5m, 10m)
* 🔍 **Search bar** to filter coins in the table
* 📑 **Table & Card views** (toggleable)
* 🖼️ **Coin icons** loaded in the background (no UI blocking)
* 🕯️ **Candlestick charts** using `mplfinance`, theme-aware colors
* ⚡ **Non-blocking fetch with QThread** (smooth UI, no freezing)
* 🌙 **Dark & Light themes** powered by [qt-material](https://github.com/UN-GCPDS/qt-material)
* 💾 **Chart caching** per coin/day to avoid redundant API calls

---

## 🔧 Installation

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/crypto-tracker.git
cd crypto-tracker
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv venv
source venv/bin/activate   # macOS/Linux
venv\Scripts\activate      # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

If you don’t have a `requirements.txt` yet, create one with:

```txt
PySide6
requests
pandas
mplfinance
matplotlib
qt-material
```

---

## ▶️ Usage

Run the app with:

```bash
python crypto_tracker.py
```

---

## 🎛 Controls

* **Search bar** → filter coins by name or symbol
* **Chart Range dropdown** → choose OHLC data range (7, 30, 90, 365 days)
* **Auto-refresh dropdown** → select update interval
* **Toggle Card/Table** → switch between card grid and data table
* **Toggle Theme** → switch between Dark/Light themes
* **Refresh Now** → manual refresh of market data
* **Click a row/card** → view candlestick chart for that coin

---

## 📦 Project Structure

```
crypto-tracker/
├── crypto_tracker.py   # Main application
├── README.md           # Documentation
└── requirements.txt    # Python dependencies
```

---

## ⚡ Tech Stack

* **Frontend/UI**: PySide6 (Qt for Python), qt-material
* **Data Visualization**: matplotlib, mplfinance
* **Backend API**: CoinGecko (REST API)
* **Data Handling**: pandas
* **Async/Threading**: QThread for non-blocking fetches

---

## 📜 License

MIT License – feel free to use and modify.

---

## 🙌 Credits

* [CoinGecko API](https://www.coingecko.com/) for crypto market data
* [qt-material](https://github.com/UN-GCPDS/qt-material) for theme styling
