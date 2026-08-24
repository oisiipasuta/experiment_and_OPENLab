document.addEventListener("DOMContentLoaded", () => {
    const audio = document.getElementById("audio-player");
    const recordButton = document.getElementById("record-button");
    const feedback = document.getElementById("record-feedback");
    const nextStep = document.getElementById("next-step");
    const nextStepMessage = document.getElementById("next-step-message");
    const nextStepLink = document.getElementById("next-step-link");
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";

    if (!audio || !recordButton || !feedback) {
        return;
    }

    let playbackFinished = false;
    let lastAllowedTime = 0;
    let suppressSeekGuard = false;

    const setFeedback = (message, isError = false) => {
        feedback.textContent = message;
        feedback.style.color = isError ? "var(--error)" : "var(--success)";
    };

    recordButton.disabled = true;

    audio.addEventListener("timeupdate", () => {
        if (!suppressSeekGuard && !audio.seeking && !playbackFinished) {
            lastAllowedTime = audio.currentTime;
        }
    });

    audio.addEventListener("play", () => {
        if (!playbackFinished) {
            recordButton.disabled = false;
            setFeedback("「ここ好き！」と思ったタイミングで押してください。");
        }
    });

    audio.addEventListener("seeking", () => {
        if (playbackFinished || suppressSeekGuard) {
            return;
        }

        if (Math.abs(audio.currentTime - lastAllowedTime) > 0.75) {
            suppressSeekGuard = true;
            audio.currentTime = lastAllowedTime;
            setFeedback("曲の途中を飛ばさず、最後まで聴いてください。", true);
            window.setTimeout(() => {
                suppressSeekGuard = false;
            }, 0);
        }
    });

    audio.addEventListener("pause", () => {
        if (playbackFinished || audio.ended || audio.currentTime === 0) {
            return;
        }

        setFeedback("再生中は一時停止せず、そのまま最後まで聴いてください。", true);
        audio.play().catch(() => {
            setFeedback("再生が止まった場合は、実験者に知らせてください。", true);
        });
    });

    window.addEventListener("beforeunload", (event) => {
        if (playbackFinished || audio.paused || audio.currentTime === 0) {
            return;
        }

        event.preventDefault();
        event.returnValue = "";
    });

    audio.addEventListener("ended", async () => {
        playbackFinished = true;
        recordButton.disabled = true;
        nextStep?.classList.remove("hidden");
        setFeedback("再生が終了しました。次の画面へ移動します。");

        try {
            const response = await fetch(recordButton.dataset.completeUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken,
                },
                body: JSON.stringify({
                    audio_duration_sec: Number.isFinite(audio.duration) ? audio.duration : null,
                }),
            });

            const data = await response.json();
            if (!response.ok || !data.ok) {
                throw new Error(data.message || "次の画面への移動に失敗しました。");
            }

            if (nextStepLink) {
                nextStepLink.href = data.next_url;
                nextStepLink.textContent = "曲全体の印象へ進む";
            }

            if (nextStepMessage) {
                nextStepMessage.textContent = "再生が終了しました。曲全体の印象を回答してください。";
            }

            window.location.href = data.next_url;
        } catch (error) {
            setFeedback(error.message || "次の画面への移動に失敗しました。下のボタンから進んでください。", true);
        }
    });

    recordButton.addEventListener("click", async () => {
        if (audio.paused && audio.currentTime === 0) {
            setFeedback("再生を開始してから押してください。", true);
            return;
        }

        recordButton.disabled = true;

        try {
            const audioTimeSec = audio.currentTime;
            const response = await fetch(recordButton.dataset.recordUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken,
                },
                body: JSON.stringify({
                    assignment_id: Number(recordButton.dataset.assignmentId),
                    audio_time_sec: audioTimeSec,
                    audio_duration_sec: Number.isFinite(audio.duration) ? audio.duration : null,
                    pressed_time: audioTimeSec,
                    performance_time_ms: performance.now(),
                    client_timestamp: new Date().toISOString(),
                }),
            });

            const data = await response.json();
            if (!response.ok || !data.ok) {
                throw new Error(data.message || "ボタンを押した時刻の保存に失敗しました。");
            }

            setFeedback(data.message);
        } catch (error) {
            setFeedback(error.message || "ボタンを押した時刻の保存に失敗しました。", true);
        } finally {
            if (!playbackFinished) {
                recordButton.disabled = false;
            }
        }
    });
});
