document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector(".rating-form, .selection-form");
    if (!form) return;

    form.addEventListener("submit", (event) => {
        if (form.dataset.submitting === "true") {
            event.preventDefault();
            return;
        }

        form.dataset.submitting = "true";
        form.querySelectorAll('button[type="submit"]').forEach((button) => {
            button.disabled = true;
        });
    });
});
