const socket = io();

const rulesScreen = document.getElementById("rules-screen");
const quizScreen = document.getElementById("quiz-screen");
const resultScreen = document.getElementById("result-screen");

const qRoundBadge = document.getElementById("q-round-badge");
const qTypeBadge = document.getElementById("q-type-badge");
const displayQText = document.getElementById("display-q-text");
const displayChoicesContainer = document.getElementById("display-choices-container");
const displayBuzzNotice = document.getElementById("display-buzz-notice");
const displayAnswerBox = document.getElementById("display-answer-box");
const displayAnswerText = document.getElementById("display-answer-text");

let textStreamTimer = null;
let dramaticTimeout = null;
let currentQuestionData = null;

socket.on("connect", () => {
    socket.emit("request_player_status");
});

socket.on("question_start_player", (data) => {
    currentQuestionData = data;
    showQuizScreen();

    if (displayBuzzNotice) displayBuzzNotice.classList.add("hidden");
    if (displayAnswerBox) displayAnswerBox.classList.add("hidden");
    if (displayChoicesContainer) {
        displayChoicesContainer.classList.add("hidden");
        displayChoicesContainer.innerHTML = "";
    }

    const qNum = data.round_q_num || 1;
    let typeName = "テキスト方式";
    if (data.type === "choice") typeName = "4択方式";
    if (data.type === "mhy") typeName = "文字選択方式";
    if (data.finish_pending) typeName += " ⚠️【ラスト問題】";

    if (qRoundBadge) qRoundBadge.innerText = `第 ${qNum} 問`;
    if (qTypeBadge) qTypeBadge.innerText = typeName;

    const dramaticOverlay = document.getElementById("dramatic-overlay");
    const dramaticNum = document.getElementById("dramatic-num");
    const dramaticType = document.getElementById("dramatic-type");

    if (dramaticOverlay && dramaticNum && dramaticType) {
        dramaticNum.innerText = `第 ${qNum} 問`;
        dramaticType.innerText = `【 ${typeName} 】`;
        dramaticOverlay.classList.remove("hidden");
        dramaticOverlay.style.display = "flex";
    }

    if (displayQText) displayQText.innerText = "";
    if (textStreamTimer) clearInterval(textStreamTimer);
    if (dramaticTimeout) clearTimeout(dramaticTimeout);

    dramaticTimeout = setTimeout(() => {
        if (dramaticOverlay) {
            dramaticOverlay.classList.add("hidden");
            dramaticOverlay.style.display = "none";
        }

        if (data.type === "choice" && data.choices && displayChoicesContainer) {
            displayChoicesContainer.classList.remove("hidden");
            data.choices.forEach((choiceText) => {
                const choiceDiv = document.createElement("div");
                choiceDiv.className = "choice-btn";
                choiceDiv.style.cursor = "default";
                choiceDiv.style.textAlign = "center";
                choiceDiv.style.fontSize = "1.5rem";
                choiceDiv.innerText = choiceText;
                displayChoicesContainer.appendChild(choiceDiv);
            });
        }

        const chars = (data.question || "").split("");
        let idx = 0;
        textStreamTimer = setInterval(() => {
            if (idx < chars.length) {
                if (displayQText) displayQText.innerText += chars[idx];
                idx++;
            } else {
                clearInterval(textStreamTimer);
            }
        }, (data.char_speed || 0.08) * 1000);
    }, 2200);
});

socket.on("player_buzzed_notice", (data) => {
    if (textStreamTimer) clearInterval(textStreamTimer);
    if (displayBuzzNotice) {
        displayBuzzNotice.innerText = `⚡️ ${data.player_name} さんが早押し！ (${data.rank}番目)`;
        displayBuzzNotice.classList.remove("hidden");
    }
});

socket.on("answer_result", (data) => {
    showAnswerResult(data);
});

socket.on("question_through", (data) => {
    showAnswerResult(data);
});

function showAnswerResult(data) {
    if (displayAnswerBox && displayAnswerText) {
        let answerStr = "";
        if (data.correct_answers && data.correct_answers.length > 0) {
            answerStr = data.correct_answers.join(" / ");
        } else if (data.correct_choice_index !== undefined && data.correct_choice_index !== null) {
            const idx = data.correct_choice_index;
            const choices = currentQuestionData ? currentQuestionData.choices : [];
            answerStr = choices[idx] ? choices[idx] : `選択肢 ${idx + 1}`;
        }
        displayAnswerText.innerText = answerStr || "-";
        displayAnswerBox.classList.remove("hidden");
    }
}

socket.on("quiz_reset_notice", () => {
    showRulesScreen();
});

socket.on("quiz_finished", (data) => {
    showResultScreen(data.rankings || []);
});

function showRulesScreen() {
    if (rulesScreen) rulesScreen.classList.remove("hidden");
    if (quizScreen) quizScreen.classList.add("hidden");
    if (resultScreen) resultScreen.classList.add("hidden");
}

function showQuizScreen() {
    if (rulesScreen) rulesScreen.classList.add("hidden");
    if (quizScreen) quizScreen.classList.remove("hidden");
    if (resultScreen) resultScreen.classList.add("hidden");
}

function showResultScreen(rankings) {
    if (rulesScreen) rulesScreen.classList.add("hidden");
    if (quizScreen) quizScreen.classList.add("hidden");
    if (resultScreen) resultScreen.classList.remove("hidden");

    const tbody = document.getElementById("display-result-list");
    if (tbody) {
        tbody.innerHTML = "";
        rankings.forEach((p) => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td style="padding: 12px; font-weight: bold; color: #ffeb3b;">${p.rank}位</td>
                <td style="padding: 12px; font-weight: bold;">${p.name}</td>
                <td style="padding: 12px; font-weight: bold; color: #00e676;">${p.score} pt</td>
            `;
            tbody.appendChild(tr);
        });
    }
}