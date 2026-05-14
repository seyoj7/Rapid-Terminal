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