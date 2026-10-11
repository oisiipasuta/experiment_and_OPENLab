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
    let hiddenCount = 0;
    let hiddenStartedAt = null;
    let hiddenDurationMs = 0;
    let seekAttemptCount = 0;
    let unexpectedPauseCount = 0;
    let playbackErrorCount = 0;
    const pendingPressRequests = new Set();
    let pressSaveQueue = Promise.resolve();
    let lastProgressSaveAt = 0;

    const setFeedback = (message, isError = false) => {
        feedback.textContent = message;
        feedback.style.color = isError ? "var(--error)" : "var(--success)";
    };

    const readApiResponse = async (response, fallbackMessage) => {
        const contentType = response.headers.get("Content-Type") || "";
        if (!contentType.toLowerCase().includes("application/json")) {
            throw new Error(
                `${fallbackMessage}（HTTP ${response.status}）。ページを再読み込みして、もう一度操作してください。`
            );
        }
        let data;
        try {
            data = await response.json();
        } catch {
            throw new Error(`${fallbackMessage}。サーバーの応答を読み取れませんでした。`);
        }
        if (!response.ok || !data?.ok) {
            throw new Error(data?.message || fallbackMessage);
        }
        return data;
    };

    const resumeAudioIfNeeded = () => {
        const resumeTime = Number(recordButton.dataset.resumeAudioTime);
        if (!Number.isFinite(resumeTime) || resumeTime <= 0 || !Number.isFinite(audio.duration)) {
            return;
        }
        const safeResumeTime = Math.min(resumeTime, Math.max(0, audio.duration - 0.05));
        if (safeResumeTime <= 0) return;
        suppressSeekGuard = true;
        audio.currentTime = safeResumeTime;
        lastAllowedTime = safeResumeTime;
        setFeedback(`前回の再生位置（${safeResumeTime.toFixed(1)} 秒）から再開します。`);
    };

    audio.addEventListener("seeked", () => {
        if (suppressSeekGuard) {
            lastAllowedTime = audio.currentTime;
            suppressSeekGuard = false;
        }
    });

    if (audio.readyState >= 1) {
        resumeAudioIfNeeded();
    } else {
        audio.addEventListener("loadedmetadata", resumeAudioIfNeeded, { once: true });
    }

    recordButton.disabled = true;

    audio.addEventListener("timeupdate", () => {
        if (!suppressSeekGuard && !audio.seeking && !playbackFinished) {
            lastAllowedTime = audio.currentTime;
        }
        if (!playbackFinished && performance.now() - lastProgressSaveAt >= 5000) {
            lastProgressSaveAt = performance.now();
            savePlaybackProgress();
        }
    });

    const savePlaybackProgress = (useBeacon = false) => {
        const payload = {
            audio_current_time_sec: audio.currentTime,
            audio_duration_sec: Number.isFinite(audio.duration) ? audio.duration : "",
            csrf_token: csrfToken,
        };
        const url = recordButton.dataset.progressUrl;
        if (useBeacon && navigator.sendBeacon) {
            const body = new URLSearchParams(payload);
            navigator.sendBeacon(url, body);
            return;
        }
        fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken,
            },
            body: JSON.stringify(payload),
            keepalive: useBeacon,
        }).catch(() => {});
    };

    audio.addEventListener("play", () => {
        if (!playbackFinished) {
            recordButton.disabled = false;
            setFeedback("「良い」と感じたタイミングでボタンを押してください。");
        }
    });

    audio.addEventListener("seeking", () => {
        if (playbackFinished || suppressSeekGuard) {
            return;
        }

        if (Math.abs(audio.currentTime - lastAllowedTime) > 0.75) {
            seekAttemptCount += 1;
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

        unexpectedPauseCount += 1;

        setFeedback("再生中は一時停止せず、そのまま最後まで聴いてください。", true);
        audio.play().catch(() => {
            setFeedback("再生が止まった場合は、実験者に知らせてください。", true);
        });
    });

    audio.addEventListener("error", () => {
        playbackErrorCount += 1;
    });

    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            hiddenCount += 1;
            hiddenStartedAt = performance.now();
        } else if (hiddenStartedAt !== null) {
            hiddenDurationMs += performance.now() - hiddenStartedAt;
            hiddenStartedAt = null;
        }
    });

    window.addEventListener("beforeunload", (event) => {
        if (!playbackFinished && !audio.paused && audio.currentTime > 0) {
            savePlaybackProgress(true);
        }
        if (playbackFinished || audio.paused || audio.currentTime === 0) {
            return;
        }

        event.preventDefault();
        event.returnValue = "";
    });

    window.addEventListener("pagehide", () => {
        if (!playbackFinished) {
            savePlaybackProgress(true);
        }
    });

    audio.addEventListener("ended", async () => {
        playbackFinished = true;
        recordButton.disabled = true;
        nextStep?.classList.remove("hidden");
        setFeedback("再生が終了しました。次の画面へ移動します。");

        try {
            // Flush click events captured before the end event before switching
            // the server-side trial phase to rating.
            await Promise.allSettled([...pendingPressRequests]);
            const finalHiddenDurationMs = hiddenDurationMs + (
                hiddenStartedAt === null ? 0 : performance.now() - hiddenStartedAt
            );
            const response = await fetch(recordButton.dataset.completeUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken,
                },
                body: JSON.stringify({
                    client_ended: true,
                    audio_duration_sec: Number.isFinite(audio.duration) ? audio.duration : null,
                    audio_current_time_sec: audio.currentTime,
                    hidden_count: hiddenCount,
                    hidden_duration_ms: Math.round(finalHiddenDurationMs),
                    seek_attempt_count: seekAttemptCount,
                    unexpected_pause_count: unexpectedPauseCount,
                    playback_error_count: playbackErrorCount,
                }),
            });

            const data = await readApiResponse(response, "次の画面への移動に失敗しました。");

            if (nextStepLink) {
                nextStepLink.href = data.next_url;
                nextStepLink.textContent = data.next_step === "selection" ? "良いと感じた部分の確認へ進む" : "回答画面へ進む";
            }

            if (nextStepMessage) {
                nextStepMessage.textContent =
                    data.next_step === "selection"
                        ? "再生が終了しました。良いと感じた部分を確認してください。"
                        : "再生が終了しました。回答画面へ進みます。";
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

        // Capture the audio position synchronously in the click handler. Keep the
        // button available while requests are in flight so rapid, distinct
        // presses are not discarded because of network latency.
        const audioTimeSec = audio.currentTime;
        let requestPromise;
        try {
            const requestBody = JSON.stringify({
                assignment_id: Number(recordButton.dataset.assignmentId),
                audio_time_sec: audioTimeSec,
                pressed_time: audioTimeSec,
                performance_time_ms: performance.now(),
                client_timestamp: new Date().toISOString(),
            });
            requestPromise = pressSaveQueue.then(() => fetch(recordButton.dataset.recordUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken,
                },
                body: requestBody,
                keepalive: true,
            }));
            pressSaveQueue = requestPromise.catch(() => {});
            pendingPressRequests.add(requestPromise);
            const response = await requestPromise;

            const data = await readApiResponse(response, "ボタンを押した時刻の保存に失敗しました。");

            setFeedback(data.message);
        } catch (error) {
            setFeedback(error.message || "ボタンを押した時刻の保存に失敗しました。", true);
        } finally {
            pendingPressRequests.delete(requestPromise);
            if (!playbackFinished) {
                recordButton.disabled = false;
            }
        }
    });
});
