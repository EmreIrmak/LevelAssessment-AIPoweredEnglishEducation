function getCtx() {
    return window.__EXAM_CONTEXT__ || {};
}

async function postTechnicalEvent(eventType, message) {
    const ctx = getCtx();
    try {
        await fetch("/api/technical_event", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                session_id: ctx.sessionId,
                module: ctx.module,
                event_type: eventType,
                message: message || null,
            }),
        });
    } catch (e) {
        // swallow
    }
}

function initTimer() {
    const badge = document.getElementById("timerBadge");
    if (!badge) return;

    const textEl = badge.querySelector('[data-role="timerText"]');

    let remaining = parseInt(badge.getAttribute("data-remaining") || "0", 10);
    if (Number.isNaN(remaining)) remaining = 0;

    const formatRemaining = (sec) => {
        const s = Math.max(0, parseInt(sec, 10) || 0);
        const m = Math.floor(s / 60);
        const r = s % 60;
        return `${m}min ${r}secs`;
    };

    // ensure correct initial render even if template text is stale
    if (textEl) textEl.textContent = formatRemaining(remaining);

    const tick = () => {
        remaining = Math.max(0, remaining - 1);
        if (textEl) textEl.textContent = formatRemaining(remaining);
        if (remaining <= 10) badge.classList.add("bg-danger");
        if (remaining === 0) {
            postTechnicalEvent("timer_expired", "Client-side timer reached 0.");
            // Let backend enforce expiry + module advance
            const ctx = getCtx();
            window.location.href = `/exam/${ctx.sessionId}`;
        }
    };

    setInterval(tick, 1000);
}

function initSpeaking() {
    const ctx = getCtx();
    if (ctx.module !== "SPEAKING") return;

    const transcriptEl = document.getElementById("speakingTranscript");
    const audioFilenameInput = document.getElementById("audioFilenameInput");
    const prepEl = document.getElementById("prepTimerText");
    const respEl = document.getElementById("respTimerText");
    const stateEl = document.getElementById("speakingState");
    const form = document.getElementById("examForm");

    if (!transcriptEl || !prepEl || !respEl || !stateEl || !form) return;

    let stream = null;
    let recorder = null;
    let chunks = [];
    let submitting = false;
    let respTimer = null;
    let prepTimer = null;

    const prepSeconds = ctx.speakingPrepSeconds || 20;
    const respSeconds = ctx.speakingResponseSeconds || 60;

    function format(sec) {
        const s = Math.max(0, Math.floor(sec));
        const m = Math.floor(s / 60);
        const r = s % 60;
        return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
    }

    function updateState(text) {
        stateEl.textContent = text;
    }

    async function startRecording() {
        try {
            chunks = [];
            stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            stream.getAudioTracks().forEach((t) => {
                t.addEventListener("ended", () => {
                    postTechnicalEvent("mic_track_ended", "Microphone track ended unexpectedly.");
                });
            });

            recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
            recorder.ondataavailable = (e) => {
                if (e.data && e.data.size > 0) chunks.push(e.data);
            };
            recorder.onerror = (e) => {
                postTechnicalEvent("mediarecorder_error", String(e.error || e.name || "unknown"));
            };
            recorder.onstop = async () => {
                try {
                    const blob = new Blob(chunks, { type: "audio/webm" });
                    const fd = new FormData();
                    fd.append("session_id", String(ctx.sessionId));
                    fd.append("question_id", String(ctx.questionId));
                    fd.append("module", ctx.module);
                    fd.append("audio", blob, "speech.webm");

                    const res = await fetch("/api/stt/transcribe", { method: "POST", body: fd });
                    const data = await res.json();
                    if (!data.ok) {
                        await postTechnicalEvent("stt_failed", data.error || data.status || "unknown");
                        alert(`Speech-to-text failed: ${data.error || data.status}`);
                        // Do not submit if STT failed
                        submitting = false;
                        return;
                    } else {
                        transcriptEl.value = data.transcript || "";
                        if (audioFilenameInput && data.audio_filename) {
                            audioFilenameInput.value = data.audio_filename;
                        }
                    }
                } catch (e) {
                    await postTechnicalEvent("stt_exception", String(e));
                    alert("A technical error occurred during speech-to-text.");
                    // Do not submit if exception occurred
                    submitting = false;
                    return;
                } finally {
                    if (stream) {
                        stream.getTracks().forEach((t) => t.stop());
                        stream = null;
                    }
                    if (!submitting) {
                        submitting = true;
                        form.submit();
                    }
                }
            };

            recorder.start();
            updateState("Recording started (60s)...");
            let remaining = respSeconds;
            respEl.textContent = format(remaining);
            respTimer = setInterval(() => {
                remaining -= 1;
                respEl.textContent = format(remaining);
                if (remaining <= 0) {
                    clearInterval(respTimer);
                    respTimer = null;
                    try {
                        if (recorder && recorder.state !== "inactive") recorder.stop();
                    } catch (e) {
                        postTechnicalEvent("mediarecorder_stop_error", String(e));
                    }
                }
            }, 1000);
        } catch (e) {
            await postTechnicalEvent("mic_access_denied", String(e));
            alert("Microphone access was not granted. Please check your browser permissions.");
        }
    }

    function startPrep() {
        updateState("Preparation time: 20s");
        let remaining = prepSeconds;
        prepEl.textContent = format(remaining);
        prepTimer = setInterval(() => {
            remaining -= 1;
            prepEl.textContent = format(Math.max(remaining, 0));
            if (remaining <= 0) {
                clearInterval(prepTimer);
                prepTimer = null;
                startRecording();
            }
        }, 1000);
    }

    startPrep();
}

function initWritingWordCount() {
    const ctx = getCtx();
    if (ctx.module !== "WRITING") return;

    const textarea = document.getElementById("writingAnswer");
    const counter = document.getElementById("writingWordCount");
    if (!textarea || !counter) return;

    const countWords = (text) => {
        const cleaned = String(text || "").trim();
        if (!cleaned) return 0;
        return cleaned.split(/\s+/).filter(Boolean).length;
    };

    const render = () => {
        const words = countWords(textarea.value);
        counter.textContent = `Word count: ${words}`;
        if (words > 0 && (words < 150 || words > 200)) {
            counter.classList.remove("text-muted");
            counter.classList.add("text-warning");
        } else {
            counter.classList.remove("text-warning");
            counter.classList.add("text-muted");
        }
    };

    textarea.addEventListener("input", render);
    render();
}

document.addEventListener("DOMContentLoaded", () => {
    initTimer();
    initSpeaking();
    initWritingWordCount();
    
    // Form validation: prevent empty speaking/writing answers before submit
    const form = document.getElementById("examForm");
    if (form) {
        form.addEventListener("submit", (e) => {
            const ctx = getCtx();
            
            // For Speaking module, require non-empty transcript
            if (ctx.module === "SPEAKING") {
                const transcriptEl = document.getElementById("speakingTranscript");
                const textAnswer = (transcriptEl?.value || "").trim();
                
                if (!textAnswer) {
                    e.preventDefault();
                    alert("Please record an answer before proceeding.");
                    return false;
                }
            }
            
            // For Writing module, optionally warn but allow
            if (ctx.module === "WRITING") {
                const writingEl = document.getElementById("writingAnswer");
                const textAnswer = (writingEl?.value || "").trim();
                
                if (!textAnswer) {
                    if (!confirm("Your answer is empty. Are you sure you want to continue?")) {
                        e.preventDefault();
                        return false;
                    }
                }
            }
        });
    }
});


