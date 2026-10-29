const socket = io();

let isHostActive = false;

const nextQBtn = document.getElementById("next-q-btn");
const resetQBtn = document.getElementById("reset-q-btn");
const finishQBtn = document.getElementById("finish-q-btn");
const difficultySelect = document.getElementById("difficulty-select");
const qTypeBadge = document.getElementById("q-type-badge");
const qText = document.getElementById("q-text");
const qAnswersContainer = document.getElementById("q-answers-container");
const qAnswersText = document.getElementById("q-answers-text");
const qStatus = document.getElementById("q-status");
const buzzInfo = document.getElementById("buzz-info");
const playerListBody = document.getElementById("player-list-body");

function setHostControlsDisabled(disabled) {
    if (nextQBtn) nextQBtn.disabled = disabled;
    if (resetQBtn) resetQBtn.disabled = disabled;
    if (finishQBtn) finishQBtn.disabled = disabled;
    if (difficultySelect) difficultySelect.disabled = disabled;
}

socket.on("connect", () => {
    socket.emit("claim_host");
});

socket.on("host_claim_result", (data) => {
    if (data && data.success) {
        isHostActive = true;
        setHostControlsDisabled(false);
        socket.emit("request_player_status");
        if (qStatus) qStatus.innerText = "状態: 🟢 ホスト権限を獲得しました（操作可能）";
    } else {
        isHostActive = false;
        setHostControlsDisabled(true);
        if (qStatus) qStatus.innerText = "状態: 🔒 他の端末でホスト操作中のためロックされています";
        alert(data && data.message ? data.message : "他の端末でホスト操作中のため操作権限が得られませんでした。");
    }
});

socket.on("host_released_notice", (data) => {
    if (!isHostActive) {
        if (confirm("ホスト操作権限が解放されました。ホスト権限を取得しますか？")) {
            socket.emit("claim_host");
        }
    }
});

if (difficultySelect) {
    difficultySelect.addEventListener("change", (e) => {
        if (!isHostActive) return;
        socket.emit("change_difficulty", { difficulty: e.target.value });
    });
}

if (nextQBtn) {
    nextQBtn.addEventListener("click", () => {
        if (!isHostActive) return;
        const diff = difficultySelect ? difficultySelect.value : 'all';
        socket.emit("start_next_question", { difficulty: diff });
    });
}

if (resetQBtn) {
    resetQBtn.addEventListener("click", () => {
        if (!isHostActive) return;
        if (confirm("配信問題数と出題履歴をリセットしますか？")) {
            socket.emit("reset_question_count");
        }
    });
}

if (finishQBtn) {
    finishQBtn.addEventListener("click", () => {
        if (!isHostActive) return;
        if (confirm("現在の問題（または待機状態）をラストにしてクイズを終了しますか？")) {
            socket.emit("finish_quiz");
        }
    });
}

socket.on("question_start_host", (data) => {
    let typeName = "テキスト方式";
    if (data.type === "choice") typeName = "4択方式";
    if (data.type === "mhy") typeName = "文字選択方式";
    
    if (qTypeBadge) {
        let badgeStr = `[ 第 ${data.round_q_num || 1} 問 ] 形式: ${typeName}`;
        if (data.finish_pending) badgeStr += " ⚠️【ラスト問】";
        qTypeBadge.innerText = badgeStr;
    }
    if (qText) qText.innerText = data.question;
    
    if (qAnswersContainer) qAnswersContainer.classList.remove("hidden");
    if (qAnswersText) {
        if (data.type === "choice") {
            const correctChoice = data.choices[data.answer_index] || "";
            qAnswersText.innerText = `${correctChoice} (選択肢 #${data.answer_index + 1})`;
        } else {
            qAnswersText.innerText = (data.answers || []).join(" / ");
        }
    }

    if (qStatus) {
        if (data.finish_pending) {
            qStatus.innerText = "状態: 最終問題の読み上げ中（解答後に自動リザルトへ移動します）";
        } else {
            qStatus.innerText = "状態: 問題読み上げ中・早押し受付中";
        }
    }
    if (buzzInfo) buzzInfo.innerText = "";
});

socket.on("player_buzzed_notice", (data) => {
    if (qStatus) qStatus.innerText = `状態: ${data.player_name} が早押し！ (解答権獲得)`;
    if (buzzInfo) {
        buzzInfo.innerText += `\n⚡️ ${data.player_name} が ${data.rank} 番目に押しました！`;
    }
});

socket.on("last_question_notice", (data) => {
    alert(data.message);
    if (qStatus) qStatus.innerText = "状態: 最終問題として実行中（解答終了後リザルトへ移行）";
});

socket.on("answer_result", (data) => {
    renderPlayers(data.players);
});

socket.on("question_through", (data) => {
    if (qStatus) qStatus.innerText = "状態: 時間切れ（スルー・誰も押しませんでした）";
    if (buzzInfo) buzzInfo.innerText = "";
});

socket.on("quiz_reset_notice", (data) => {
    alert(data.message);
    if (qTypeBadge) qTypeBadge.innerText = "[ リセット済み ]";
});

socket.on("host_error", (data) => {
    alert(data.message);
});

socket.on("update_players", (players) => {
    renderPlayers(players);
});

socket.on("quiz_finished", (data) => {
    const mainScreen = document.getElementById("main-screen");
    const resultScreen = document.getElementById("result-screen");
    const resultList = document.getElementById("result-list");

    if (mainScreen) mainScreen.classList.add("hidden");
    if (resultScreen) resultScreen.classList.remove("hidden");

    if (resultList) {
        resultList.innerHTML = "";
        (data.rankings || []).forEach((p) => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${p.rank}位</td>
                <td>${p.name}</td>
                <td>${p.score} pt</td>
            `;
            resultList.appendChild(tr);
        });
    }
});

function renderPlayers(players) {
    if (!playerListBody) return;
    playerListBody.innerHTML = "";
    
    const sorted = Object.entries(players).sort((a, b) => b[1].score - a[1].score);
    
    sorted.forEach(([pid, p], idx) => {
        const tr = document.createElement("tr");
        
        const rankTd = document.createElement("td");
        rankTd.innerText = `${idx + 1}位`;
        
        const nameTd = document.createElement("td");
        nameTd.innerText = p.name || "ゲスト";
        
        const scoreTd = document.createElement("td");
        scoreTd.innerText = `${p.score || 0} pt`;
        
        const comboTd = document.createElement("td");
        comboTd.innerText = `${p.combo || 0} 連勝`;
        
        const connTd = document.createElement("td");
        connTd.innerText = (p.is_connected !== false) ? "🟢 オンライン" : "🔴 離脱";

        const actionTd = document.createElement("td");
        const kickBtn = document.createElement("button");
        kickBtn.className = "btn btn-danger btn-sm";
        kickBtn.innerText = "削除";
        kickBtn.disabled = !isHostActive;
        kickBtn.onclick = () => {
            if (!isHostActive) return;
            if (confirm(`「${p.name}」さんを削除しますか？`)) {
                socket.emit("kick_player", { player_id: pid });
            }
        };
        actionTd.appendChild(kickBtn);
        
        tr.appendChild(rankTd);
        tr.appendChild(nameTd);
        tr.appendChild(scoreTd);
        tr.appendChild(comboTd);
        tr.appendChild(connTd);
        tr.appendChild(actionTd);
        
        playerListBody.appendChild(tr);
    });
}