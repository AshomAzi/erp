document.addEventListener("DOMContentLoaded", () => {
    const clockElements = document.querySelectorAll("[data-live-clock]");

    function updateClocks() {
        const now = new Date();
        const formatted = now.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        });
        clockElements.forEach((element) => {
            element.textContent = formatted;
        });
    }

    if (clockElements.length > 0) {
        updateClocks();
        setInterval(updateClocks, 1000);
    }

    const menuToggle = document.getElementById("menuToggle");
    const sidebar = document.getElementById("sidebar");
    const sidebarClose = document.getElementById("sidebarClose");

    function setSidebarOpen(isOpen) {
        if (!sidebar || !menuToggle) return;
        sidebar.classList.toggle("open", isOpen);
        menuToggle.setAttribute("aria-expanded", String(isOpen));
    }

    if (menuToggle && sidebar) {
        menuToggle.addEventListener("click", () => {
            setSidebarOpen(!sidebar.classList.contains("open"));
        });
    }

    if (sidebarClose) {
        sidebarClose.addEventListener("click", () => setSidebarOpen(false));
    }

    document.addEventListener("click", (event) => {
        if (
            sidebar &&
            sidebar.classList.contains("open") &&
            event.target instanceof Node &&
            !sidebar.contains(event.target) &&
            (!menuToggle || !menuToggle.contains(event.target))
        ) {
            setSidebarOpen(false);
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && sidebar && sidebar.classList.contains("open")) {
            setSidebarOpen(false);
        }
    });

    const tabButtons = document.querySelectorAll("[data-tab-target]");
    const tabSections = document.querySelectorAll(".tab-section");
    const activeTabStorageKey = `coreerp.activeTab.${window.location.pathname}`;

    function activateTab(targetId) {
        const targetButton = Array.from(tabButtons).find(
            (button) => button.getAttribute("data-tab-target") === targetId
        );
        const targetSection = Array.from(tabSections).find((section) => section.id === targetId);
        if (!targetButton || !targetSection) return false;

        tabButtons.forEach((tabButton) => tabButton.classList.remove("active"));
        targetButton.classList.add("active");

        tabSections.forEach((section) => {
            section.classList.toggle("active", section.id === targetId);
        });
        return true;
    }

    tabButtons.forEach((button) => {
        button.addEventListener("click", () => {
            const targetId = button.getAttribute("data-tab-target");
            activateTab(targetId);

            try {
                window.sessionStorage.setItem(activeTabStorageKey, targetId);
            } catch (error) {
                console.error("Unable to remember the active tab.", error);
            }

            setSidebarOpen(false);
        });
    });

    if (tabButtons.length > 0) {
        // Re-open the section the user was on before a refresh or form submit.
        try {
            const savedTab = window.sessionStorage.getItem(activeTabStorageKey);
            if (savedTab) activateTab(savedTab);
        } catch (error) {
            console.error("Unable to restore the active tab.", error);
        }

        // Always start at the top of the page (stop the browser restoring the old scroll position).
        if ("scrollRestoration" in window.history) {
            window.history.scrollRestoration = "manual";
        }
        window.scrollTo(0, 0);
        window.addEventListener("load", () => window.scrollTo(0, 0));
        window.addEventListener("pageshow", () => window.scrollTo(0, 0));
    }

    document.querySelectorAll("[data-modal-open]").forEach((trigger) => {
        trigger.addEventListener("click", () => {
            const modalId = trigger.getAttribute("data-modal-open");
            const modal = document.getElementById(modalId);
            if (modal instanceof HTMLDialogElement) modal.showModal();
            else if (modal) modal.classList.add("open");
        });
    });

    document.querySelectorAll("[data-modal-close]").forEach((closer) => {
        closer.addEventListener("click", () => {
            const modal = closer.closest("dialog.modal-backdrop");
            if (modal instanceof HTMLDialogElement && modal.open) modal.close();
        });
    });

    document.querySelectorAll(".modal-backdrop").forEach((backdrop) => {
        backdrop.addEventListener("click", (event) => {
            if (event.target === backdrop && backdrop instanceof HTMLDialogElement) {
                backdrop.close();
            }
        });
    });

    document.querySelectorAll("[data-profile-picture-input]").forEach((input) => {
        const footer = input.closest(".sidebar-footer");
        const trigger = footer && footer.querySelector("[data-profile-picture-trigger]");
        const image = footer && footer.querySelector("[data-profile-image]");
        const initials = footer && footer.querySelector("[data-profile-initials]");
        const feedback = footer && footer.querySelector("[data-profile-picture-feedback]");
        const uploadUrl = input.dataset.uploadUrl;
        const profileName = footer && footer.querySelector(".profile-details strong");

        if (initials && profileName) {
            const parts = profileName.textContent.trim().split(/\s+/).filter(Boolean);
            const calculatedInitials = parts
                .slice(0, 2)
                .map((part) => part.charAt(0).toUpperCase())
                .join("");
            if (calculatedInitials) {
                initials.textContent = calculatedInitials;
            }
        }

        if (
            !(input instanceof HTMLInputElement) ||
            !(trigger instanceof HTMLButtonElement) ||
            !(image instanceof HTMLImageElement) ||
            !(initials instanceof HTMLElement) ||
            !(feedback instanceof HTMLElement) ||
            !uploadUrl
        ) {
            console.error("Profile picture controls are missing a required element or upload URL.");
            return;
        }

        const showFeedback = (message) => {
            feedback.textContent = message;
        };
        const showPicture = (source) => {
            image.src = source;
            image.hidden = false;
            initials.hidden = true;
            trigger.textContent = "Change profile picture";
        };
        const showInitials = () => {
            image.hidden = true;
            initials.hidden = false;
            trigger.textContent = "Upload profile picture";
        };
        const getCsrfToken = () => {
            const field = document.querySelector("input[name='csrfmiddlewaretoken']");
            if (field) return field.value;
            const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
            return match ? decodeURIComponent(match[1]) : "";
        };

        // If the saved picture cannot be loaded, fall back to the initials.
        image.addEventListener("error", showInitials);

        trigger.addEventListener("click", () => input.click());
        input.addEventListener("change", async () => {
            const file = input.files && input.files[0];
            if (!file) return;

            const acceptedTypes = ["image/jpeg", "image/png", "image/webp", "image/gif"];
            if (!acceptedTypes.includes(file.type)) {
                showFeedback("Choose a JPEG, PNG, WebP, or GIF image.");
                input.value = "";
                return;
            }
            if (file.size > 1024 * 1024) {
                showFeedback("Choose an image smaller than 1 MB.");
                input.value = "";
                return;
            }

            const formData = new FormData();
            formData.append("profile_picture", file);

            trigger.disabled = true;
            showFeedback("Uploading picture...");
            try {
                const response = await fetch(uploadUrl, {
                    method: "POST",
                    body: formData,
                    headers: {
                        "X-CSRFToken": getCsrfToken(),
                        "X-Requested-With": "XMLHttpRequest",
                    },
                    credentials: "same-origin",
                });
                const result = await response.json().catch(() => ({}));
                if (!response.ok) {
                    showFeedback(result.error || "The picture could not be uploaded.");
                    return;
                }
                showPicture(result.url);
                showFeedback("Profile picture updated.");
            } catch (error) {
                console.error("Unable to upload the profile picture.", error);
                showFeedback("The picture could not be uploaded. Check your connection and try again.");
            } finally {
                trigger.disabled = false;
                input.value = "";
            }
        });
    });

    document.querySelectorAll("[data-table-search]").forEach((input) => {
        const tableId = input.getAttribute("data-table-search");
        const table = document.getElementById(tableId);
        if (!table) return;

        input.addEventListener("input", () => {
            const term = input.value.toLowerCase().trim();
            table.querySelectorAll("tbody tr").forEach((row) => {
                const match = row.textContent.toLowerCase().includes(term);
                row.classList.toggle("is-filtered-out", !match);
            });
        });
    });
});