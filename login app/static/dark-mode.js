// Dark Mode Management Script

function ensureDarkModeToggle() {
    if (document.querySelector('.dark-mode-toggle')) {
        return;
    }

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'dark-mode-toggle dark-mode-toggle--floating';
    button.setAttribute('aria-label', 'Toggle dark mode');
    button.innerHTML = '<i class="fa-solid fa-moon"></i>';
    button.addEventListener('click', toggleDarkMode);
    document.body.appendChild(button);
}

// Initialize dark mode on page load
document.addEventListener('DOMContentLoaded', function() {
    ensureDarkModeToggle();

    const isDarkMode = localStorage.getItem('darkMode') === 'true';
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    // Use localStorage value or fallback to system preference
    if (isDarkMode || (!localStorage.getItem('darkMode') && prefersDark)) {
        enableDarkMode();
    }
    
    // Listen for system theme changes
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        if (!localStorage.getItem('darkMode')) {
            if (e.matches) {
                enableDarkMode();
            } else {
                disableDarkMode();
            }
        }
    });
});

// Toggle dark mode function
function toggleDarkMode() {
    const htmlElement = document.documentElement;
    const isDarkMode = htmlElement.classList.contains('dark-mode');
    
    if (isDarkMode) {
        disableDarkMode();
    } else {
        enableDarkMode();
    }
}

// Enable dark mode
function enableDarkMode() {
    document.documentElement.classList.add('dark-mode');
    localStorage.setItem('darkMode', 'true');
    updateDarkModeButton(true);
}

// Disable dark mode
function disableDarkMode() {
    document.documentElement.classList.remove('dark-mode');
    localStorage.setItem('darkMode', 'false');
    updateDarkModeButton(false);
}

// Update dark mode button appearance
function updateDarkModeButton(isDarkMode) {
    const buttons = document.querySelectorAll('.dark-mode-toggle');
    buttons.forEach(button => {
        const icon = button.querySelector('i');
        if (icon) {
            if (isDarkMode) {
                icon.className = 'fa-solid fa-sun';
                button.setAttribute('aria-label', 'Switch to light mode');
                button.title = 'Light Mode';
            } else {
                icon.className = 'fa-solid fa-moon';
                button.setAttribute('aria-label', 'Switch to dark mode');
                button.title = 'Dark Mode';
            }
        }
    });
}
