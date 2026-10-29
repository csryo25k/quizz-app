const socket = io();

let playerId = localStorage.getItem("quiz_player_id");
if (!playerId) {
    playerId = "p_" + Math.random().toString(36).substr(2, 9);
    localStorage.setItem("quiz_player_id", playerId);
}

let currentQuestion = null;
let currentFullQuestionText = "";
let myFrozenText = null;
let textAnimationTimer = null;
let answerTimer = null;
let buzzTimer = null;
let dramaticTimer = null;
let currentStepId = 0;

let pendingCorrectAnswer = null;
let isAnswering = false;

const setupScreen = document.getElementById("setup-screen");
const gameScreen = document.getElementById("game-screen");
const nameInput = document.getElementById("player-name");
const joinBtn = document.getElementById("join-btn");

const displayName = document.getElementById("display-name");
const displayScore = document.getElementById("display-score");
const displayCombo = document.getElementById("display-combo");

const qBox = document.getElementById("question-box");
const timerBox = document.getElementById("timer-box");
const timerCount = document.getElementById("timer-count");
const timerBar = document.getElementById("timer-bar");

const buzzBtn = document.getElementById("buzz-btn");
const resultMsg = document.getElementById("result-message");

const answerUI = document.getElementById("answer-ui");
const uiChoice = document.getElementById("ui-choice");
const uiMhy = document.getElementById("ui-mhy");
const uiText = document.getElementById("ui-text");
const textInput = document.getElementById("text-answer-input");
const textSubmitBtn = document.getElementById("text-submit-btn");

window.addEventListener("load", () => {
    const savedName = localStorage.getItem("quiz_player_name");
    if (savedName && nameInput) {
        nameInput.value = savedName;
    }
});

if (joinBtn) joinBtn.addEventListener("click", registerPlayer);
if (textSubmitBtn) textSubmitBtn.addEventListener("click", submitTextAnswer);

if (textInput) {
    textInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            submitTextAnswer();
        }
    });
}

if (nameInput) {
    nameInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            registerPlayer();
        }
    });
}

document.addEventListener("keydown", (e) => {
    if (e.code === "Space" || e.key === " ") {
        const activeEl = document.activeElement;
        if (activeEl && (activeEl.tagName === "INPUT" || activeEl.tagName === "TEXTAREA")) {
            return;
        }
        e.preventDefault();
        if (buzzBtn && !buzzBtn.disabled) {
            triggerBuzz();
        }
    }
});

function registerPlayer() {
    const name = nameInput.value.trim() || "ゲスト";
    localStorage.setItem("quiz_player_name", name);
    socket.emit("join_player", { player_id: playerId, name: name });
}

socket.on("player_registered", (data) => {
    if (setupScreen) setupScreen.classList.add("hidden");
    if (gameScreen) gameScreen.classList.remove("hidden");
    if (displayName) displayName.innerText = data.name;
    if (displayScore) displayScore.innerText = data.score;
    if (displayCombo) displayCombo.innerText = data.combo;
});

socket.on("kicked", (data) => {
    alert(data && data.message ? data.message : "ホストによってキックされました。");
    localStorage.removeItem("quiz_player_id");
    localStorage.removeItem("quiz_player_name");
    location.reload();
});

if (buzzBtn) buzzBtn.addEventListener("click", triggerBuzz);

function triggerBuzz() {
    if (buzzBtn) buzzBtn.disabled = true;
    socket.emit("buzz", { player_id: playerId });
}

function checkAndShowCorrectAnswer() {
    const isBuzzActive = buzzBtn && !buzzBtn.disabled;
    if (pendingCorrectAnswer && !isBuzzActive && !isAnswering) {
        displayCorrectAnswer(pendingCorrectAnswer);
        pendingCorrectAnswer = null;
    }
}

function displayCorrectAnswer(data) {
    const box = document.getElementById("correct-answer-box");
    if (!box || !data) return;

    let answerStr = "";
    if (data.correct_answers && data.correct_answers.length > 0) {
        answerStr = data.correct_answers.join(" / ");
    } else if (data.correct_choice_index !== undefined && data.correct_choice_index !== null) {
        const idx = data.correct_choice_index;
        const currentChoices = currentQuestion ? currentQuestion.choices : [];
        answerStr = (currentChoices && currentChoices[idx]) ? currentChoices[idx] : `選択肢 ${idx + 1}`;
    }

    if (answerStr) {
        box.innerText = `💡 正解: ${answerStr}`;
        box.classList.remove("hidden");
    }
}

function hideCorrectAnswer() {
    const box = document.getElementById("correct-answer-box");
    if (box) {
        box.innerText = "";
        box.classList.add("hidden");
    }
}

socket.on("question_start_player", (data) => {
    currentQuestion = data;
    currentFullQuestionText = data.question || "";
    myFrozenText = null;
    isAnswering = false;
    pendingCorrectAnswer = null;
    hideCorrectAnswer();
    resetAllUI();

    const qNum = data.round_q_num || 1;
    let typeName = "テキスト方式";
    if (data.type === "choice") typeName = "4択方式";
    if (data.type === "mhy") typeName = "文字選択方式";
    if (data.finish_pending) typeName += " ⚠️【ラスト問題】";

    const dramaticOverlay = document.getElementById("dramatic-overlay");
    const dramaticNum = document.getElementById("dramatic-num");
    const dramaticType = document.getElementById("dramatic-type");

    if (dramaticOverlay && dramaticNum && dramaticType) {
        dramaticNum.innerText = `第 ${qNum} 問`;
        dramaticType.innerText = `【 ${typeName} 】`;
        dramaticOverlay.classList.remove("hidden");
        dramaticOverlay.style.display = "flex";
    }

    if (qBox) qBox.innerText = "";
    if (buzzBtn) buzzBtn.disabled = true;

    if (dramaticTimer) clearTimeout(dramaticTimer);

    dramaticTimer = setTimeout(() => {
        if (dramaticOverlay) {
            dramaticOverlay.classList.add("hidden");
            dramaticOverlay.style.display = "none";
        }
        if (buzzBtn) buzzBtn.disabled = false;

        const chars = data.question.split("");
        let idx = 0;
        
        if (textAnimationTimer) clearInterval(textAnimationTimer);
        
        textAnimationTimer = setInterval(() => {
            if (idx < chars.length) {
                if (qBox) qBox.innerText += chars[idx];
                idx++;
            } else {
                clearInterval(textAnimationTimer);
                startBuzzTimer(data.buzz_limit_sec || 5.0);
            }
        }, (data.char_speed || 0.08) * 1000);
    }, 2200);
});

function startBuzzTimer(limitSec) {
    if (buzzTimer) clearInterval(buzzTimer);
    if (timerBox) timerBox.classList.remove("hidden");

    const startTime = Date.now();
    const durationMs = limitSec * 1000;

    buzzTimer = setInterval(() => {
        const elapsed = Date.now() - startTime;
        const remaining = Math.max(0, (durationMs - elapsed) / 1000);
        
        if (timerCount) timerCount.innerText = `残り: ${remaining.toFixed(1)} 秒`;
        if (timerBar) timerBar.style.width = Math.min(100, (remaining / limitSec) * 100) + "%";

        if (remaining <= 0) {
            clearInterval(buzzTimer);
            if (buzzBtn) buzzBtn.disabled = true;
            checkAndShowCorrectAnswer();
        }
    }, 50);
}

socket.on("buzz_success_me", (data) => {
    isAnswering = true;
    if (textAnimationTimer) clearInterval(textAnimationTimer);
    if (buzzTimer) clearInterval(buzzTimer);
    
    if (data.frozen_question_text) {
        myFrozenText = data.frozen_question_text;
    }
    if (qBox && myFrozenText !== null) {
        qBox.innerText = myFrozenText;
    }

    const buzzStatusMsg = document.getElementById("buzz-status-msg");
    if (buzzStatusMsg) {
        buzzStatusMsg.innerText = `⚡️ あなたは ${data.rank} 番目に押しました！`;
    }

    currentStepId = data.step_id || 0;
    showAnswerUI(data.type, data.limit, data.mhy_choices, data.choices);
});

function showAnswerUI(type, limit, mhyChoices, choices) {
    if (answerUI) answerUI.classList.remove("hidden");
    startAnswerTimer(limit);

    if (type === "choice" && uiChoice) {
        uiChoice.classList.remove("hidden");
        uiChoice.innerHTML = "";
        (choices || []).forEach((choiceText) => {
            const btn = document.createElement("button");
            btn.className = "choice-btn";
            btn.innerText = choiceText;
            btn.onclick = () => submitAnswer(choiceText);
            uiChoice.appendChild(btn);
        });
    } else if (type === "mhy" && uiMhy) {
        uiMhy.classList.remove("hidden");
        const enteredEl = document.getElementById("mhy-entered");
        if (enteredEl) enteredEl.innerText = "";
        renderMhyStepChoices(mhyChoices);
    } else if (type === "text" && uiText) {
        uiText.classList.remove("hidden");
        if (textInput) {
            textInput.value = "";
            textInput.focus();
        }
    }
}

function renderMhyStepChoices(choices) {
    const grid = document.getElementById("mhy-choice-grid");
    if (!grid) return;
    grid.innerHTML = "";
    (choices || []).forEach((char) => {
        const btn = document.createElement("button");
        btn.className = "choice-btn";
        btn.innerText = char;
        btn.onclick = () => {
            socket.emit("submit_mhy_step", { player_id: playerId, char: char });
        };
        grid.appendChild(btn);
    });
}

socket.on("mhy_next_step", (data) => {
    const enteredEl = document.getElementById("mhy-entered");
    if (enteredEl) enteredEl.innerText = data.entered;
    
    currentStepId = data.step_id;
    startAnswerTimer(data.limit || 3.0);
    renderMhyStepChoices(data.choices);
});

function startAnswerTimer(limitSec) {
    if (answerTimer) clearInterval(answerTimer);
    if (timerBox) timerBox.classList.remove("hidden");

    const startTime = Date.now();
    const durationMs = limitSec * 1000;

    answerTimer = setInterval(() => {
        const elapsed = Date.now() - startTime;
        const remaining = Math.max(0, (durationMs - elapsed) / 1000);

        if (timerCount) timerCount.innerText = `解答残り: ${remaining.toFixed(1)} 秒`;
        if (timerBar) timerBar.style.width = Math.max(0, (remaining / limitSec) * 100) + "%";

        if (remaining <= 0) {
            clearInterval(answerTimer);
            isAnswering = false;
            socket.emit("answer_timeout", { player_id: playerId, step_id: currentStepId });
            resetAnswerUI();
            checkAndShowCorrectAnswer();
        }
    }, 50);
}

function submitAnswer(answer) {
    if (answerTimer) clearInterval(answerTimer);
    socket.emit("submit_answer", { player_id: playerId, answer: answer });
    resetAnswerUI();
}

function submitTextAnswer() {
    if (!textInput) return;
    const answer = textInput.value.trim();
    if (!answer) return;
    submitAnswer(answer);
}

socket.on("answer_submitted_ack", (data) => {
    isAnswering = false;
    resetAllUI();
    if (qBox) qBox.innerText = currentFullQuestionText;
    if (resultMsg) {
        resultMsg.classList.remove("hidden");
        if (data.is_timeout || !data.is_correct) {
            resultMsg.className = "result-box result-incorrect";
            resultMsg.innerText = `❌ 不正解... (${data.gained_score} pt)`;
        } else {
            resultMsg.className = "result-box result-correct";
            resultMsg.innerText = `⭕ 正解！ (+${data.gained_score} pt)`;
        }
    }
    if (displayScore) displayScore.innerText = data.score;

    checkAndShowCorrectAnswer();
});

socket.on("answer_result", (data) => {
    if (qBox) qBox.innerText = currentFullQuestionText;
    pendingCorrectAnswer = data;
    checkAndShowCorrectAnswer();
});

socket.on("question_through", (data) => {
    if (qBox) qBox.innerText = currentFullQuestionText;
    pendingCorrectAnswer = data;
    checkAndShowCorrectAnswer();
});

socket.on("last_question_notice", (data) => {
    const buzzStatusMsg = document.getElementById("buzz-status-msg");
    if (buzzStatusMsg) {
        buzzStatusMsg.innerText = "⚠️ ホストが終了を指定しました。現在の問題で終了となります。";
    }
});

function resetAnswerUI() {
    if (answerUI) answerUI.classList.add("hidden");
    if (uiChoice) uiChoice.classList.add("hidden");
    if (uiMhy) uiMhy.classList.add("hidden");
    if (uiText) uiText.classList.add("hidden");
    if (timerBox) timerBox.classList.add("hidden");
}

function resetAllUI() {
    resetAnswerUI();
    if (resultMsg) resultMsg.classList.add("hidden");
    if (buzzBtn) buzzBtn.disabled = true;
    if (textAnimationTimer) clearInterval(textAnimationTimer);
    if (answerTimer) clearInterval(answerTimer);
    if (buzzTimer) clearInterval(buzzTimer);
    if (dramaticTimer) clearTimeout(dramaticTimer);
}

socket.on("quiz_finished", (data) => {
    if (gameScreen) gameScreen.classList.add("hidden");
    const resultScreen = document.getElementById("result-screen");
    if (resultScreen) resultScreen.classList.remove("hidden");

    let myRank = "-";
    let myScore = 0;
    const rankingList = document.getElementById("ranking-list");
    if (rankingList) {
        rankingList.innerHTML = "";
        (data.rankings || []).forEach((p) => {
            const isMe = p.player_id === playerId;
            if (isMe) {
                myRank = p.rank;
                myScore = p.score;
            }
            const tr = document.createElement("tr");
            if (isMe) tr.style.backgroundColor = "#fff3cd";
            tr.innerHTML = `
                <td>${p.rank}位</td>
                <td>${p.name} ${isMe ? '(あなた)' : ''}</td>
                <td>${p.score} pt</td>
            `;
            rankingList.appendChild(tr);
        });
    }

    const myFinalResult = document.getElementById("my-final-result");
    if (myFinalResult) {
        myFinalResult.innerText = `あなたの順位: ${myRank}位 (${myScore} pt)`;
    }
});