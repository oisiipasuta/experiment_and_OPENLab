document.addEventListener("DOMContentLoaded", () => {
    const tabButtons = Array.from(document.querySelectorAll("[data-admin-tab]"));
    const tabPanels = Array.from(document.querySelectorAll("[data-admin-panel]"));
    const practiceToggle = document.querySelector("[data-hide-practice-toggle]");
    const participantFilter = document.querySelector("[data-participant-filter]");
    const participantCards = Array.from(
        document.querySelectorAll('[data-practice-container="participant-card"]')
    );
    const simpleParticipantEntries = Array.from(
        document.querySelectorAll(
            "[data-participant-entry]:not([data-song-response-row]):not([data-practice-container='participant-card'])"
        )
    );
    const songResponseRows = Array.from(document.querySelectorAll("[data-song-response-row]"));
    const songCards = Array.from(document.querySelectorAll("[data-song-summary-card]"));
    const heatmapRows = Array.from(document.querySelectorAll("[data-heatmap-row]"));
    const overviewSongChips = Array.from(document.querySelectorAll("[data-song-overview-chip]"));
    const songMetaRows = Array.from(document.querySelectorAll("[data-song-meta-row]"));
    const practiceStorageKey = "music-experiment-admin-hide-practice";
    const participantStorageKey = "music-experiment-admin-participant-filter";
    const heatmapClasses = [
        "heatmap-empty",
        "heatmap-1",
        "heatmap-2",
        "heatmap-3",
        "heatmap-4",
        "heatmap-5",
        "heatmap-6",
    ];

    if (tabButtons.length === 0 || tabPanels.length === 0) {
        return;
    }

    const setHiddenState = (element, shouldHide) => {
        element.classList.toggle("practice-hidden", shouldHide);
        element.hidden = shouldHide;
    };

    const activateTab = (tabName) => {
        tabButtons.forEach((button) => {
            button.classList.toggle("active", button.dataset.adminTab === tabName);
        });

        tabPanels.forEach((panel) => {
            panel.classList.toggle("active", panel.dataset.adminPanel === tabName);
        });
    };

    const songKey = (songId, isPractice) => `${songId}::${isPractice}`;

    const parseScore = (value) => {
        const numeric = Number(value);
        return Number.isFinite(numeric) ? numeric : null;
    };

    const scoreToPercent = (score) => {
        if (score === null) {
            return 0;
        }
        return (((score - 1.0) / 6.0) * 100.0).toFixed(2);
    };

    const scoreToHeatmapClass = (score) => {
        if (score === null) {
            return "heatmap-empty";
        }
        if (score < 2.0) {
            return "heatmap-1";
        }
        if (score < 3.0) {
            return "heatmap-2";
        }
        if (score < 4.0) {
            return "heatmap-3";
        }
        if (score < 5.0) {
            return "heatmap-4";
        }
        if (score < 6.0) {
            return "heatmap-5";
        }
        return "heatmap-6";
    };

    const shouldHideForPractice = (element, hidePractice) =>
        hidePractice && element.dataset.isPractice === "true";

    const shouldHideForParticipant = (element, selectedParticipant) =>
        Boolean(selectedParticipant) && element.dataset.participantId !== selectedParticipant;

    const collectVisibleSongRows = (selectedParticipant, hidePractice) => {
        const visibleRowsBySong = new Map();

        songResponseRows.forEach((row) => {
            const shouldHide =
                shouldHideForPractice(row, hidePractice) ||
                shouldHideForParticipant(row, selectedParticipant);
            setHiddenState(row, shouldHide);

            if (shouldHide) {
                return;
            }

            const key = songKey(row.dataset.songId, row.dataset.isPractice);
            if (!visibleRowsBySong.has(key)) {
                visibleRowsBySong.set(key, []);
            }
            visibleRowsBySong.get(key).push(row);
        });

        return visibleRowsBySong;
    };

    const updateSongCard = (card, visibleRows, selectedParticipant, hidePractice) => {
        const metaText = card.querySelector(".meta-text");
        const phaseLabel = card.dataset.isPractice === "true" ? "練習試行" : "本試行";
        const responseCount = selectedParticipant
            ? visibleRows.length
            : Number(card.dataset.initialResponseCount || "0");
        const pressCount = selectedParticipant
            ? visibleRows.filter((row) => row.dataset.hasPress === "true").length
            : Number(card.dataset.initialPressCount || "0");

        if (metaText) {
            metaText.textContent = `${phaseLabel} / 回答 ${responseCount} 件 / ボタン押下 ${pressCount} 件`;
        }

        card.querySelectorAll("[data-score-name]").forEach((item) => {
            const scoreName = item.dataset.scoreName;
            const values = visibleRows
                .map((row) => parseScore(row.getAttribute(`data-score-${scoreName}`)))
                .filter((value) => value !== null);
            const average =
                values.length > 0
                    ? values.reduce((sum, value) => sum + value, 0) / values.length
                    : null;

            const valueElement = item.querySelector("[data-average-value]");
            const fillElement = item.querySelector("[data-average-fill]");

            if (valueElement) {
                valueElement.textContent = average === null ? "-" : average.toFixed(2);
            }
            if (fillElement) {
                fillElement.style.width = `${scoreToPercent(average)}%`;
            }
        });

        const shouldHide =
            shouldHideForPractice(card, hidePractice) ||
            (Boolean(selectedParticipant) && responseCount === 0);
        setHiddenState(card, shouldHide);
    };

    const updateHeatmapRow = (row, visibleRows, selectedParticipant, hidePractice) => {
        const responseCountElement = row.querySelector("[data-heatmap-response-count]");
        const responseCount = selectedParticipant
            ? visibleRows.length
            : Number(row.dataset.initialResponseCount || "0");
        if (responseCountElement) {
            responseCountElement.textContent = String(responseCount);
        }

        row.querySelectorAll("[data-heatmap-cell]").forEach((cell) => {
            const scoreName = cell.dataset.scoreName;
            const values = visibleRows
                .map((entry) => parseScore(entry.getAttribute(`data-score-${scoreName}`)))
                .filter((value) => value !== null);
            const average =
                values.length > 0
                    ? values.reduce((sum, value) => sum + value, 0) / values.length
                    : null;
            const className = scoreToHeatmapClass(average);

            heatmapClasses.forEach((name) => cell.classList.remove(name));
            cell.classList.add(className);
            cell.textContent = average === null ? "-" : average.toFixed(1);
            cell.title =
                average === null ? `${scoreName}: no data` : `${scoreName}: ${average.toFixed(2)}`;
        });

        const shouldHide =
            shouldHideForPractice(row, hidePractice) ||
            (Boolean(selectedParticipant) && responseCount === 0);
        setHiddenState(row, shouldHide);
    };

    const updateOverviewSongChip = (chip, visibleRows, selectedParticipant, hidePractice) => {
        const responseCount = selectedParticipant
            ? visibleRows.length
            : Number(chip.dataset.initialResponseCount || "0");
        chip.textContent = `${chip.dataset.songId} / 回答 ${responseCount}`;
        const shouldHide =
            shouldHideForPractice(chip, hidePractice) ||
            (Boolean(selectedParticipant) && responseCount === 0);
        setHiddenState(chip, shouldHide);
    };

    const updateSongMetaRow = (row, visibleRows, selectedParticipant, hidePractice) => {
        const shouldHide =
            shouldHideForPractice(row, hidePractice) ||
            (Boolean(selectedParticipant) && visibleRows.length === 0);
        setHiddenState(row, shouldHide);
    };

    const updateParticipantCards = (selectedParticipant, hidePractice) => {
        participantCards.forEach((card) => {
            const participantMismatch = shouldHideForParticipant(card, selectedParticipant);
            const detailEntries = Array.from(card.querySelectorAll("[data-practice-entry]"));

            detailEntries.forEach((entry) => {
                setHiddenState(entry, shouldHideForPractice(entry, hidePractice));
            });

            const hasVisibleEntry =
                detailEntries.length === 0 ||
                detailEntries.some((entry) => !entry.classList.contains("practice-hidden"));

            setHiddenState(card, participantMismatch || !hasVisibleEntry);
        });
    };

    const updateSimpleEntries = (selectedParticipant, hidePractice) => {
        simpleParticipantEntries.forEach((entry) => {
            const shouldHide =
                shouldHideForPractice(entry, hidePractice) ||
                shouldHideForParticipant(entry, selectedParticipant);
            setHiddenState(entry, shouldHide);
        });
    };

    const applyFilters = () => {
        const hidePractice = Boolean(practiceToggle && practiceToggle.checked);
        const selectedParticipant = participantFilter ? participantFilter.value : "";

        updateSimpleEntries(selectedParticipant, hidePractice);
        updateParticipantCards(selectedParticipant, hidePractice);

        const visibleRowsBySong = collectVisibleSongRows(selectedParticipant, hidePractice);

        songCards.forEach((card) => {
            const key = songKey(card.dataset.songId, card.dataset.isPractice);
            updateSongCard(card, visibleRowsBySong.get(key) || [], selectedParticipant, hidePractice);
        });

        heatmapRows.forEach((row) => {
            const key = songKey(row.dataset.songId, row.dataset.isPractice);
            updateHeatmapRow(row, visibleRowsBySong.get(key) || [], selectedParticipant, hidePractice);
        });

        overviewSongChips.forEach((chip) => {
            const key = songKey(chip.dataset.songId, chip.dataset.isPractice);
            updateOverviewSongChip(
                chip,
                visibleRowsBySong.get(key) || [],
                selectedParticipant,
                hidePractice
            );
        });

        songMetaRows.forEach((row) => {
            const key = songKey(row.dataset.songId, row.dataset.isPractice);
            updateSongMetaRow(row, visibleRowsBySong.get(key) || [], selectedParticipant, hidePractice);
        });

        window.localStorage.setItem(practiceStorageKey, hidePractice ? "true" : "false");
        if (participantFilter) {
            window.localStorage.setItem(participantStorageKey, selectedParticipant);
        }
    };

    tabButtons.forEach((button) => {
        button.addEventListener("click", () => activateTab(button.dataset.adminTab));
    });

    if (practiceToggle) {
        const savedPracticePreference = window.localStorage.getItem(practiceStorageKey);
        if (savedPracticePreference !== null) {
            practiceToggle.checked = savedPracticePreference === "true";
        }
        practiceToggle.addEventListener("change", applyFilters);
    }

    if (participantFilter) {
        const savedParticipantFilter = window.localStorage.getItem(participantStorageKey);
        if (savedParticipantFilter !== null) {
            participantFilter.value = savedParticipantFilter;
        }
        participantFilter.addEventListener("change", applyFilters);
    }

    applyFilters();
});
