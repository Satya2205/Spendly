// main.js — students will add JavaScript here as features are built

// ------------------------------------------------------------------ //
// Video modal                                                          //
// ------------------------------------------------------------------ //
// Click "See how it works" → open a modal with an embedded YouTube     //
// iframe. Close on button, overlay, or Escape. The iframe `src` is      //
// attached on open and cleared on close so the video fully stops.      //
// ------------------------------------------------------------------ //

(function () {
    "use strict";

    var VIDEO_URL = "https://www.youtube.com/embed/dQw4w9WgXcQ?autoplay=1&rel=0";

    var modal   = document.getElementById("videoModal");
    var frame   = document.getElementById("videoModalFrame");
    var openers = document.querySelectorAll("[data-open-video-modal]");
    var closers = document.querySelectorAll("[data-close-video-modal]");

    if (!modal || !frame) { return; }

    function openModal() {
        modal.hidden = false;
        document.body.classList.add("modal-open");
        frame.src = VIDEO_URL;
    }

    function closeModal() {
        modal.hidden = true;
        document.body.classList.remove("modal-open");
        // Clear src so the YouTube iframe fully stops playing.
        // Setting to "" is the standard no-API way to stop playback.
        frame.src = "";
    }

    openers.forEach(function (btn) {
        btn.addEventListener("click", openModal);
    });

    closers.forEach(function (btn) {
        btn.addEventListener("click", closeModal);
    });

    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && !modal.hidden) {
            closeModal();
        }
    });
})();
