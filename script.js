const coinCards = document.querySelectorAll(".coin-card");

coinCards.forEach(card => {
    card.addEventListener("click", () => {

        coinCards.forEach(item => {
            item.classList.remove("active-coin");
        });

        card.classList.add("active-coin");

    });
});