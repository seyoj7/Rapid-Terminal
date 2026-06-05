const coins = [
  { pair: "BTC/USDT", symbol: "BTCUSDT", price: 0, change: 0 },
  { pair: "ETH/USDT", symbol: "ETHUSDT", price: 0, change: 0 },
  { pair: "SOL/USDT", symbol: "SOLUSDT", price: 0, change: 0 },
];

let currentInterval = "15m";
let activeCoin = coins[0];

const selectedToken = document.querySelector(".selected-token");

const ticker = document.querySelector(".market-ticker");

coins.forEach((coin, index) => {
    const card = document.createElement("div");
    card.classList.add("coin-card");
    if (index === 0) card.classList.add("active-coin");
    card.textContent = `${coin.pair} $${coin.price} ${coin.change > 0 ? "+" : ""}${coin.change}%`;
  
    card.addEventListener("click", () => {
        document.querySelectorAll(".coin-card").forEach(c => c.classList.remove("active-coin"));
        card.classList.add("active-coin");
        selectedToken.textContent = card.textContent;
        activeCoin = coins[index];
        resetFutureWhitespace();
        fetchCandles(activeCoin, currentInterval);
    });
  
    ticker.appendChild(card);

    selectedToken.textContent = document.querySelector(".active-coin").textContent;
});

const navOptions = document.querySelectorAll(".nav-option");

const timeframes = document.querySelectorAll(".timeframe");

timeframes.forEach(frame => {
    frame.addEventListener("click", () => {

        timeframes.forEach(item => {
            item.classList.remove("active-timeframe");
        });

        frame.classList.add("active-timeframe");
        currentInterval = frame.textContent;
        resetFutureWhitespace();
        fetchCandles(activeCoin, currentInterval);

    });
});

const selectednav = document.querySelector(".selected-nav");

selectednav.textContent = document.querySelector(".active-option").textContent;

navOptions.forEach(item => {
    item.addEventListener("click", () => {

        navOptions.forEach(item => {
            item.classList.remove("active-option");
        });

        item.classList.add("active-option");

        selectednav.textContent = item.textContent;

    });
});

const chartProperties = {
    layout: {
        background: { color: '#222222' },
        textColor: '#ffffff',
    },
    grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0)' },
        horzLines: { color: 'rgba(255, 255, 255, 0)' },
    },
    rightPriceScale: {
        visible: true,
        borderVisible: false,
        scaleMargins: {
            top: 0.1,
            bottom: 0.1,
        },
    },
    timeScale: {
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 40,
        barSpacing: 6,
        minBarSpacing: 0.5,
        fixLeftEdge: false,
        fixRightEdge: false,
        lockVisibleTimeRangeOnResize: false,
        borderVisible: true,
        borderColor: 'rgba(255, 255, 255, 0.1)',
    },
    localization: {
        timeFormatter: (timestamp) => {
            const isIntraday = currentInterval.endsWith('m') || currentInterval.endsWith('h');
            const date = new Date(timestamp * 1000);
            if (isIntraday) {
                return new Intl.DateTimeFormat('en-IN', {
                    timeZone: 'Asia/Kolkata',
                    hour: '2-digit',
                    minute: '2-digit',
                    day: '2-digit',
                    month: 'short',
                }).format(date);
            }
            return new Intl.DateTimeFormat('en-IN', {
                timeZone: 'Asia/Kolkata',
                year: 'numeric',
                month: 'short',
                day: '2-digit',
            }).format(date);
        },
    },
}

const domElement = document.getElementById('tvcharts');
const chart = LightweightCharts.createChart(domElement, {
    ...chartProperties,
    width: domElement.clientWidth,
    height: domElement.clientHeight,
});
const candleSeries = chart.addCandlestickSeries();

const whitespaceSeries = chart.addLineSeries({
    color: 'transparent',
    lineWidth: 0,
    crosshairMarkerVisible: false,
    lastValueVisible: false,
    priceLineVisible: false,
    autoscaleInfoProvider: () => null,
});

let chartWs = null;
let futureAnchorTime = 0;

const resizeChart = () => {
    const width = domElement.clientWidth;
    const height = domElement.clientHeight;
    if (width > 0 && height > 0) {
        chart.resize(width, height);
    }
};

const resizeObserver = new ResizeObserver(resizeChart);
resizeObserver.observe(domElement);
window.addEventListener("resize", resizeChart);


function parseIntervalSecs(interval) {
    const n = parseInt(interval);
    if (interval.endsWith('m')) return n * 60;
    if (interval.endsWith('h')) return n * 3600;
    if (interval.endsWith('d')) return n * 86400;
    if (interval.endsWith('w')) return n * 7 * 86400;
    return 60;
}

function extendFutureWhitespace(fromTimeSec, interval, count = 100) {
    const step = parseIntervalSecs(interval);
    if (fromTimeSec < futureAnchorTime && fromTimeSec !== 0) {
        whitespaceSeries.setData([]);
        futureAnchorTime = 0;
    }
    const start = Math.max(fromTimeSec, futureAnchorTime);
    for (let i = 1; i <= count; i++) {
        const t = start + step * i;
        whitespaceSeries.update({ time: t });
        futureAnchorTime = t;
    }
}


function resetFutureWhitespace() {
    futureAnchorTime = 0;
    whitespaceSeries.setData([]);
}


chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
    if (!range || futureAnchorTime === 0) return;
    const step = parseIntervalSecs(currentInterval);
    const edgeTime = futureAnchorTime;
    const totalBars = chart.timeScale().getVisibleRange();
    if (!totalBars) return;
    const rightTimeSec = totalBars.to;
    if (typeof rightTimeSec === 'number' && edgeTime - rightTimeSec < step * 30) {
        extendFutureWhitespace(futureAnchorTime, currentInterval, 100);
    }
});

const API_BASE = "http://localhost:5000";
const WS_BASE  = "ws://localhost:5000";

fetchCandles(activeCoin, currentInterval);

function fetchCandles(coin, interval) {
    const url = `${API_BASE}/api/candles?symbol=${coin.symbol}&interval=${interval}&limit=250`;

    fetch(url)
        .then(res => {
            if (!res.ok) throw new Error(`API error ${res.status}: ${res.statusText}`);
            return res.json();
        })
        .then(candles => {
            candleSeries.setData(candles);

            chart.priceScale('right').applyOptions({ autoScale: true });

            const lastTime = candles[candles.length - 1].time;
            extendFutureWhitespace(lastTime, interval);

            connectChartWebSocket(coin, interval);
        })
        .catch(err => {
            console.error("[Rapid Terminal] Failed to fetch candles:", err);
            console.warn("Make sure the Python server is running: python server.py");
        });
}

function connectWebSocket(coin, index) {
    const ws = new WebSocket(`${WS_BASE}/ws/ticker/${coin.symbol.toLowerCase()}`);

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        coin.price  = data.price;
        coin.change = data.change;

        const card = document.querySelectorAll(".coin-card")[index];
        card.textContent = `${coin.pair} $${coin.price} ${coin.change > 0 ? "+" : ""}${coin.change}%`;

        const activeIndex = [...document.querySelectorAll(".coin-card")].findIndex(c => c.classList.contains("active-coin"));
        if (activeIndex === index) {
            selectedToken.textContent = card.textContent;
        }
    };
}

function connectChartWebSocket(coin, interval) {
    if (chartWs) {
        chartWs.close();
    }

    chartWs = new WebSocket(`${WS_BASE}/ws/chart/${coin.symbol.toLowerCase()}/${interval}`);

    chartWs.onmessage = (event) => {
        const candle = JSON.parse(event.data);

        candleSeries.update({
            time:  candle.time,
            open:  candle.open,
            high:  candle.high,
            low:   candle.low,
            close: candle.close,
        });

        if (candle.closed) {
            extendFutureWhitespace(candle.time, currentInterval);
        }
    };
}

coins.forEach((coin, index) => connectWebSocket(coin, index));