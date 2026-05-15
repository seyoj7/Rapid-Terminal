const coins = [
  { pair: "BTC/USDT", symbol: "BTCUSDT", price: 0, change: 0 },
  { pair: "ETH/USDT", symbol: "ETHUSDT", price: 0, change: 0 },
  { pair: "SOL/USDT", symbol: "SOLUSDT", price: 0, change: 0 },
];

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
        if (coins[index].cdata) {
            candleSeries.setData(coins[index].cdata);
        }
    });
  
    ticker.appendChild(card);

    selectedToken.textContent = document.querySelector(".active-coin").textContent;
});

const navOptions = document.querySelectorAll(".nav-option");

navOptions.forEach(card => {
    card.addEventListener("click", () => {

        navOptions.forEach(item => {
            item.classList.remove("active-option");
        });

        card.classList.add("active-option");

    });
});

const timeframes = document.querySelectorAll(".timeframe");

timeframes.forEach(frame => {
    frame.addEventListener("click", () => {

        timeframes.forEach(item => {
            item.classList.remove("active-timeframe");
        });

        frame.classList.add("active-timeframe");

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

const log = console.log;

const chartProperties ={
    layout: {
        background: { color: '#000000' },
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
    timeScale:{
        timeVisible:true,
        secondsVisible:false,
    }
}

const domElement = document.getElementById('tvcharts');
const chart = LightweightCharts.createChart(domElement, {
    ...chartProperties,
    width: domElement.clientWidth,
    height: domElement.clientHeight,
});
const candleSeries = chart.addCandlestickSeries();

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

coins.forEach((coin, index) => {
    fetch(`https://api.binance.com/api/v3/klines?symbol=${coin.symbol}&interval=1m&limit=100`)
        .then(res => res.json())
        .then(data => {
            const cdata = data.map(d => ({
                time: d[0]/1000, open: parseFloat(d[1]),
                high: parseFloat(d[2]), low: parseFloat(d[3]), close: parseFloat(d[4])
            }));

            const firstOpen = cdata[0].open;
            const latestClose = cdata[cdata.length - 1].close;
            const change = ((latestClose - firstOpen) / firstOpen * 100).toFixed(2);

            coin.price = latestClose.toFixed(2);
            coin.change = parseFloat(change);

            const card = document.querySelectorAll(".coin-card")[index];
            card.textContent = `${coin.pair} $${coin.price} ${coin.change > 0 ? "+" : ""}${coin.change}%`;

            coin.cdata = cdata;

            if (index === 0) {
                candleSeries.setData(cdata);
                selectedToken.textContent = card.textContent;
            }
        })
        .catch(err => log(err));
});