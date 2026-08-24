document.addEventListener("DOMContentLoaded", () => {
    const audio = document.getElementById("selection-audio-player");
    const seekButtons = document.querySelectorAll(".seek-button");
    const previewRanges = document.querySelectorAll("[data-preview-range]");

    if (!audio || seekButtons.length === 0) {
        return;
    }

    let previewEndTime = null;

    const formatSeconds = (value) => Number(value).toFixed(3);

    const getPreviewWindow = (element, duration) => {
        const rawStart = Number(element.dataset.previewStart || "0");
        const rawEnd = Number(element.dataset.previewEnd || "0");
        let start = Number.isFinite(rawStart) ? Math.max(0, rawStart) : 0;
        let end = Number.isFinite(rawEnd) && rawEnd > start ? rawEnd : start + 4;

        if (Number.isFinite(duration) && duration > 0) {
            start = Math.min(start, duration);
            end = Math.min(Math.max(end, start), duration);
        }

        return { start, end };
    };

    const updatePreviewRanges = () => {
        previewRanges.forEach((label) => {
            const { start, end } = getPreviewWindow(label, audio.duration);
            label.textContent = `もう一度聴く部分 ${formatSeconds(start)} - ${formatSeconds(end)} 秒`;
        });
    };

    previewRanges.forEach((label) => {
        label.textContent = "もう一度聴く部分を準備中";
    });

    audio.addEventListener("timeupdate", () => {
        if (previewEndTime !== null && audio.currentTime >= previewEndTime) {
            audio.pause();
            previewEndTime = null;
        }
    });

    audio.addEventListener("loadedmetadata", updatePreviewRanges);
    audio.addEventListener("durationchange", updatePreviewRanges);

    if (audio.readyState >= 1) {
        updatePreviewRanges();
    }

    seekButtons.forEach((button) => {
        button.addEventListener("click", () => {
            const { start, end } = getPreviewWindow(button, audio.duration);

            previewEndTime = end;
            audio.currentTime = start;
            void audio.play();
        });
    });
});
