const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../static/js/player.js"), "utf8");

function setupPlayer(response) {
    const audioEvents = {};
    const buttonEvents = {};
    const audio = {
        readyState: 1, duration: 30, currentTime: 3.3, paused: false,
        addEventListener: (name, callback) => { audioEvents[name] = callback; },
    };
    const button = {
        dataset: { assignmentId: "1", recordUrl: "/api/button-press", completeUrl: "/api/trials/1/complete-playback" },
        addEventListener: (name, callback) => { buttonEvents[name] = callback; },
    };
    const feedback = { style: {} };
    const requests = [];
    const window = { addEventListener() {}, location: {} };
    const elements = { "audio-player": audio, "record-button": button, "record-feedback": feedback };
    vm.runInNewContext(source, {
        document: {
            getElementById: (id) => elements[id] || null,
            querySelector: () => ({ content: "test-csrf" }),
            addEventListener(name, callback) { if (name === "DOMContentLoaded") callback(); },
        },
        window,
        performance: { now: () => 5000 },
        fetch: async (url, options) => { requests.push({ url, options }); return response; },
    });
    return { audioEvents, buttonEvents, button, feedback, requests, window };
}

test("HTML error response shows actionable feedback without JSON parsing", async () => {
    let jsonCalled = false;
    const player = setupPlayer({
        status: 400, ok: false,
        headers: new Headers({ "Content-Type": "text/html; charset=utf-8" }),
        json() { jsonCalled = true; throw new SyntaxError("Unexpected token '<'"); },
    });
    await player.buttonEvents.click();
    assert.equal(jsonCalled, false);
    assert.match(player.feedback.textContent, /HTTP 400/);
    assert.match(player.feedback.textContent, /再読み込み/);
    assert.equal(player.button.disabled, false);
});

test("JSON CSRF error displays server message", async () => {
    const player = setupPlayer({
        status: 400, ok: false,
        headers: new Headers({ "Content-Type": "application/json" }),
        json: async () => ({ ok: false, message: "ページを再読み込みしてください。" }),
    });
    await player.buttonEvents.click();
    assert.equal(player.feedback.textContent, "ページを再読み込みしてください。");
});

test("successful press retains captured audio time and CSRF header", async () => {
    const player = setupPlayer({
        status: 200, ok: true,
        headers: new Headers({ "Content-Type": "application/json" }),
        json: async () => ({ ok: true, message: "記録しました。" }),
    });
    await player.buttonEvents.click();
    assert.equal(player.feedback.textContent, "記録しました。");
    assert.equal(JSON.parse(player.requests[0].options.body).audio_time_sec, 3.3);
    assert.equal(player.requests[0].options.headers["X-CSRFToken"], "test-csrf");
});

test("playback completion handles HTML error without navigating", async () => {
    const player = setupPlayer({
        status: 500, ok: false,
        headers: new Headers({ "Content-Type": "text/html" }),
        json() { throw new SyntaxError("Unexpected token '<'"); },
    });
    await player.audioEvents.ended();
    assert.match(player.feedback.textContent, /HTTP 500/);
    assert.match(player.feedback.textContent, /再読み込み/);
    assert.equal(player.window.location.href, undefined);
});
