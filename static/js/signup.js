document.addEventListener("DOMContentLoaded", () => {
    const signupForm = document.getElementById("signupForm");
    if (!signupForm) return;

    signupForm.addEventListener("submit", (event) => {
        const pass = document.getElementById("password").value;
        const confirmPass = document.getElementById("confirmPassword").value;
        const errorBox = document.getElementById("signupError");

        if (pass !== confirmPass) {
            event.preventDefault();
            if (errorBox) {
                errorBox.textContent = "Passwords do not match. Please re-enter.";
                errorBox.classList.add("show");
            }
        }
    });
});
