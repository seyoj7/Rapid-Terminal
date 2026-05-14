const coinCards = document.querySelectorAll(".coin-card");

coinCards.forEach(card => {
    card.addEventListener("click", () => {

        coinCards.forEach(item => {
            item.classList.remove("active-coin");
        });

        card.classList.add("active-coin");

    });
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