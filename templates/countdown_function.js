// Function to calculate and display the remaining time
function updateCountdown() {
    // Get the current time in milliseconds since epoch
    const now = new Date().getTime();

    // Calculate the time difference in milliseconds
    const distance = targetTime - now;

    // Check if the countdown is finished
    if (distance < 0) {
        clearInterval(countdownInterval);
        displayElement.textContent = "COUNTDOWN COMPLETE!";
        return;
    }

    // Time calculations for days, hours, minutes, and seconds
    // 1 day = 24 * 60 * 60 * 1000 milliseconds
    const day_ms = 1000 * 60 * 60 * 24;
    // 1 hour = 60 * 60 * 1000 milliseconds
    const hour_ms = 1000 * 60 * 60;
    // 1 minute = 60 * 1000 milliseconds
    const minute_ms = 1000 * 60;

    // Calculate components
    const hours = Math.floor((distance % day_ms) / hour_ms);
    const minutes = Math.floor((distance % hour_ms) / minute_ms);
    const seconds = Math.floor((distance % minute_ms) / 1000);

    // Helper function to pad a number with a leading zero if it's less than 10
    const pad = (num) => String(num).padStart(2, '0');

    // Format the output as DD:HH:MM:SS
    const formattedTime =
        `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;

    // Update the display
    displayElement.textContent = formattedTime;
}

// Run the function immediately to avoid a 1-second delay at the start
updateCountdown();

// Set up the interval to run the update every second
const countdownInterval = setInterval(updateCountdown, 1000);
