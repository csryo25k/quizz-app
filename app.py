import eventlet
eventlet.monkey_patch()

import os
import time
import random
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from config import (
    QUESTIONS_FILE, TIME_LIMIT_THROUGH, AUTO_ADVANCE_DELAY,
    DIFFICULTY_LEVELS, DIFFICULTY_RATES
)
from question_loader import load_questions
from game_manager import GameManager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
template_dir = os.path.join(BASE_DIR, 'templates')
static_dir = os.path.join(BASE_DIR, 'static')

if not os.path.exists(template_dir):
    template_dir = os.path.join(os.path.dirname(BASE_DIR), 'templates')
if not os.path.exists(static_dir):
    static_dir = os.path.join(os.path.dirname(BASE_DIR), 'static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.config['SECRET_KEY'] = 'quiz_secret_key_ver14'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

game = GameManager()
used_question_ids = set()
current_difficulty = "all"

active_host_sid = None
BUZZ_TIME_LIMIT = 5.0

auto_advance_active = False
auto_advance_token = 0
finish_after_current_q = False

def is_authenticated_host():
    return active_host_sid is not None and request.sid == active_host_sid

def is_valid_player_session(player_id):
    if not player_id:
        return False
    player_info = game.players.get(player_id)
    if not player_info:
        return False
    return player_info.get('sid') == request.sid

def safe_load_questions(difficulty=None):
    try:
        raw_questions = load_questions(QUESTIONS_FILE, "all")
        if not isinstance(raw_questions, list):
            return []
        
        valid_questions = []
        for idx, q in enumerate(raw_questions):
            if not isinstance(q, dict):
                continue
            
            q_id = q.get('id', idx + 1)
            q_text = str(q.get('question', ''))
            q_type = q.get('type', 'text')
            sheet_name = q.get('sheet', 'normal')
            if q_type not in ('text', 'choice', 'mhy'):
                q_type = 'text'
                
            item = {'id': q_id, 'question': q_text, 'type': q_type, 'sheet': sheet_name, 'difficulty': sheet_name}
            
            if q_type == 'choice':
                choices = q.get('choices', [])
                if not isinstance(choices, list) or len(choices) == 0:
                    choices = ["選択肢1", "選択肢2", "選択肢3", "選択肢4"]
                else:
                    choices = [str(c) for c in choices]
                
                ans_idx = q.get('answer_index', 0)
                try:
                    ans_idx = int(ans_idx)
                except (ValueError, TypeError):
                    ans_idx = 0
                if ans_idx < 0 or ans_idx >= len(choices):
                    ans_idx = 0
                    
                item['choices'] = choices
                item['answer_index'] = ans_idx
                
            elif q_type in ('text', 'mhy'):
                answers = q.get('answers', [])
                if isinstance(answers, (str, int, float)):
                    answers = [str(answers)]
                elif isinstance(answers, list):
                    answers = [str(a) for a in answers if a is not None]
                else:
                    answers = []
                    
                if not answers and 'answer' in q:
                    answers = [str(q['answer'])]
                if not answers:
                    answers = ["正解"]
                    
                item['answers'] = answers
                if 'dummy_chars' in q:
                    item['dummy_chars'] = q['dummy_chars']
            
            valid_questions.append(item)
        return valid_questions
    except Exception as e:
        print(f"[Warning] Excel読み込み失敗: {e}")
        return []

def select_question_by_rate(available_questions, difficulty_mode):
    rates = DIFFICULTY_RATES.get(difficulty_mode, DIFFICULTY_RATES.get("all", [10, 15, 40, 25, 10]))
    
    level_map = {lvl: [] for lvl in DIFFICULTY_LEVELS}
    for q in available_questions:
        lvl = q.get('sheet') or q.get('difficulty', 'normal')
        if lvl in level_map:
            level_map[lvl].append(q)
        else:
            level_map['normal'].append(q)
            
    valid_levels = []
    weights = []
    for idx, lvl in enumerate(DIFFICULTY_LEVELS):
        if level_map[lvl] and idx < len(rates) and rates[idx] > 0:
            valid_levels.append(lvl)
            weights.append(rates[idx])
            
    if not valid_levels:
        for lvl in DIFFICULTY_LEVELS:
            if level_map[lvl]:
                valid_levels.append(lvl)
                weights.append(1)
                
    if not valid_levels:
        return random.choice(available_questions) if available_questions else None
        
    chosen_level = random.choices(valid_levels, weights=weights, k=1)[0]
    return random.choice(level_map[chosen_level])

def get_next_random_question():
    global used_question_ids
    questions = safe_load_questions()
    if not questions:
        return None, 0, 0, False

    valid_ids = {q['id'] for q in questions}
    used_question_ids = {qid for qid in used_question_ids if qid in valid_ids}
    available_questions = [q for q in questions if q['id'] not in used_question_ids]

    reset_occurred = False
    if not available_questions:
        used_question_ids.clear()
        available_questions = list(questions)
        reset_occurred = True

    qdata = select_question_by_rate(available_questions, current_difficulty)
    if not qdata:
        return None, 0, 0, False

    used_question_ids.add(qdata['id'])

    current_num = len(used_question_ids)
    total_count = len(questions)
    return qdata, current_num, total_count, reset_occurred

@app.route('/player')
def player_index():
    return render_template('player.html')

@app.route('/host')
def host_index():
    return render_template('host.html')

@app.route('/display')
def display_index():
    return render_template('display.html')

@app.route('/')
def index():
    return render_template('player.html')

@socketio.on('claim_host')
def handle_claim_host():
    global active_host_sid
    if active_host_sid is None or active_host_sid == request.sid:
        active_host_sid = request.sid
        emit('host_claim_result', {'success': True, 'message': 'あなたが現在のアクティブホストです。'})
    else:
        emit('host_claim_result', {'success': False, 'message': '現在、他の端末でホスト操作が行われています。操作権限はロックされています。'})

@socketio.on('request_player_status')
def handle_request_player_status():
    emit('update_players', game.players)

@socketio.on('join_player')
def handle_join(data):
    player_id = data.get('player_id')
    name = data.get('name', 'ゲスト')
    if player_id:
        if player_id in game.kicked_player_ids:
            emit('kicked', {'message': 'あなたはホストによってキックされています。'})
            return

        success = game.register_player(player_id, name, request.sid)
        if not success:
            emit('answer_failed', {'message': 'このプレイヤーIDは他の端末で使用されています。'})
            return

        player_info = game.players.get(player_id, {})
        emit('player_registered', {
            'player_id': player_id,
            'name': player_info.get('name'),
            'score': player_info.get('score', 0),
            'combo': player_info.get('combo', 0)
        })
        socketio.emit('update_players', game.players)

@socketio.on('kick_player')
def handle_kick_player(data):
    if not is_authenticated_host():
        emit('host_error', {'message': 'ホスト権限がありません。'})
        return
    player_id = data.get('player_id')
    if player_id:
        kicked_sid = game.kick_player(player_id)
        if kicked_sid:
            socketio.emit('kicked', {'message': 'ホストによってキックされました。'}, room=kicked_sid)
        socketio.emit('update_players', game.players)

def trigger_start_question():
    global auto_advance_active
    auto_advance_active = True
    qdata, current_idx, total_count, reset_occurred = get_next_random_question()
    if not qdata:
        socketio.emit('host_error', {'message': '問題データが読み込めません。'})
        return

    if reset_occurred:
        socketio.emit('quiz_reset_notice', {'message': '全問題を出題し切ったため出題履歴を周回・リセットしました。'})

    char_speed = 0.08
    extra_sec = BUZZ_TIME_LIMIT
    game.start_question(qdata, char_speed=char_speed, extra_buzz_sec=extra_sec)

    curr_q = game.current_question
    q_token = game.current_q_token

    socketio.emit('question_start_host', {
        'id': curr_q['id'],
        'question': curr_q['question'],
        'type': curr_q['type'],
        'answers': curr_q.get('answers', []),
        'choices': curr_q.get('choices', []),
        'answer_index': curr_q.get('answer_index'),
        'index': current_idx,
        'total': total_count,
        'round_q_num': game.round_q_count,
        'char_speed': char_speed,
        'finish_pending': finish_after_current_q
    })

    socketio.emit('question_start_player', {
        'id': curr_q['id'],
        'question': curr_q['question'],
        'type': curr_q['type'],
        'choices': curr_q.get('choices', []),
        'char_speed': char_speed,
        'extra_buzz_sec': extra_sec,
        'buzz_limit_sec': extra_sec,
        'round_q_num': game.round_q_count,
        'finish_pending': finish_after_current_q
    })

    def monitor_question_status():
        while game.current_q_token == q_token and not game.phase_finished:
            if game.should_finish_question():
                finish_answer_phase()
                break
            eventlet.sleep(0.2)

    eventlet.spawn(monitor_question_status)

@socketio.on('change_difficulty')
def handle_change_difficulty(data):
    if not is_authenticated_host():
        emit('host_error', {'message': 'ホスト権限がありません。'})
        return
    global current_difficulty, used_question_ids
    if isinstance(data, dict):
        new_diff = data.get('difficulty', 'all')
        if new_diff != current_difficulty:
            current_difficulty = new_diff
            used_question_ids.clear()

@socketio.on('start_next_question')
def handle_start_next_question(data=None):
    if not is_authenticated_host():
        emit('host_error', {'message': 'ホスト権限がありません。'})
        return
    global auto_advance_active, auto_advance_token, current_difficulty, finish_after_current_q
    finish_after_current_q = False
    if isinstance(data, dict) and 'difficulty' in data:
        new_diff = data.get('difficulty', 'all')
        if new_diff != current_difficulty:
            current_difficulty = new_diff
            used_question_ids.clear()
    auto_advance_active = True
    auto_advance_token += 1
    trigger_start_question()

@socketio.on('reset_question_count')
def handle_reset_question_count():
    if not is_authenticated_host():
        emit('host_error', {'message': 'ホスト権限がありません。'})
        return
    global used_question_ids, auto_advance_active, auto_advance_token, finish_after_current_q
    auto_advance_active = False
    finish_after_current_q = False
    auto_advance_token += 1
    used_question_ids.clear()
    game.reset_round()
    socketio.emit('quiz_reset_notice', {'message': '配信問題数と出題履歴をリセットしました。'})
    socketio.emit('update_players', game.players)

def schedule_auto_advance():
    global auto_advance_active, auto_advance_token, finish_after_current_q
    if finish_after_current_q:
        auto_advance_active = False
        finish_after_current_q = False
        def delayed_finish():
            eventlet.sleep(3.0)
            send_quiz_finished()
        eventlet.spawn(delayed_finish)
        return

    if not auto_advance_active:
        return

    auto_advance_token += 1
    current_token = auto_advance_token
    delay = AUTO_ADVANCE_DELAY

    def auto_worker():
        global auto_advance_active
        eventlet.sleep(delay)
        if auto_advance_active and auto_advance_token == current_token:
            trigger_start_question()

    eventlet.spawn(auto_worker)

def spawn_answer_timeout_checker(player_id, limit_sec, step_id=None):
    q_token = game.current_q_token
    def check_player_answer_timeout():
        eventlet.sleep(limit_sec + 1.0)
        if game.current_q_token == q_token and player_id not in game.submitted_answers:
            success, gained_score, _ = game.process_timeout(player_id, step_id=step_id)
            if success:
                socketio.emit('answer_submitted_ack', {
                    'is_correct': False,
                    'is_timeout': True,
                    'gained_score': gained_score,
                    'score': game.players.get(player_id, {}).get('score', 0)
                }, room=game.players.get(player_id, {}).get('sid'))
                
                player_name = game.players.get(player_id, {}).get('name', 'プレイヤー')
                socketio.emit('player_incorrect_notice', {
                    'player_id': player_id,
                    'player_name': player_name,
                    'message': f'{player_name}さんはタイムアウト（不正解）でした。'
                })
                socketio.emit('update_players', game.players)

                if game.should_finish_question():
                    finish_answer_phase()

    eventlet.spawn(check_player_answer_timeout)

@socketio.on('buzz')
def handle_buzz(data):
    player_id = data.get('player_id')
    if not is_valid_player_session(player_id):
        emit('answer_failed', {'message': '不正なアクセスです。'})
        return
    if not game.question_active or game.phase_finished:
        emit('answer_failed', {'message': '早押し受付時間は終了しています。'})
        return
    if player_id in game.submitted_answers:
        emit('answer_failed', {'message': 'すでに回答済みです。'})
        return
    if player_id in game.active_answers:
        emit('answer_failed', {'message': '現在回答入力中です。'})
        return

    rank, buzz_bonus, limit_sec, frozen_text, mhy_choices, step_id, player_choices = game.process_buzz(player_id)
    if rank == 999:
        emit('answer_failed', {'message': '早押し受付時間は終了しています。'})
        return

    emit('buzz_success_me', {
        'rank': rank,
        'buzz_bonus': buzz_bonus,
        'limit': limit_sec,
        'type': game.current_question['type'],
        'choices': player_choices if game.current_question['type'] == 'choice' else game.current_question.get('choices', []),
        'mhy_choices': mhy_choices,
        'frozen_question_text': frozen_text,
        'step_id': step_id
    })

    player_name = game.players.get(player_id, {}).get('name', 'プレイヤー')
    socketio.emit('player_buzzed_notice', {
        'player_id': player_id,
        'player_name': player_name,
        'rank': rank,
        'frozen_question_text': frozen_text
    })

    spawn_answer_timeout_checker(player_id, limit_sec, step_id=step_id)

@socketio.on('submit_mhy_step')
def handle_submit_mhy_step(data):
    player_id = data.get('player_id')
    if not is_valid_player_session(player_id):
        return
    char = data.get('char')

    valid, is_complete, is_correct, entered, next_choices, limit_sec, gained_score, _, new_step_id = game.process_mhy_step(player_id, char)

    # 連打による2回目以降の無効リクエスト(valid=False)は完全に無視
    if not valid:
        return

    if is_complete:
        emit('answer_submitted_ack', {
            'is_correct': is_correct,
            'is_timeout': False,
            'gained_score': gained_score,
            'score': game.players.get(player_id, {}).get('score', 0)
        })
        player_name = game.players.get(player_id, {}).get('name', 'プレイヤー')
        if not is_correct:
            socketio.emit('player_incorrect_notice', {
                'player_id': player_id,
                'player_name': player_name,
                'message': f'{player_name}さんは不正解でした。'
            })
        socketio.emit('update_players', game.players)
        if game.should_finish_question():
            finish_answer_phase()
    else:
        emit('mhy_next_step', {
            'entered': entered,
            'choices': next_choices,
            'limit': limit_sec,
            'step_id': new_step_id
        })
        spawn_answer_timeout_checker(player_id, limit_sec, step_id=new_step_id)

@socketio.on('submit_answer')
def handle_submit_answer(data):
    player_id = data.get('player_id')
    if not is_valid_player_session(player_id):
        emit('answer_failed', {'message': '不正なアクセスです。'})
        return
    answer = data.get('answer')

    success, is_correct, gained_score, _ = game.process_answer(player_id, answer)

    if not success:
        emit('answer_failed', {'message': is_correct})
        return

    emit('answer_submitted_ack', {
        'is_correct': is_correct,
        'is_timeout': False,
        'gained_score': gained_score,
        'score': game.players.get(player_id, {}).get('score', 0)
    })

    player_name = game.players.get(player_id, {}).get('name', 'プレイヤー')
    if not is_correct:
        socketio.emit('player_incorrect_notice', {
            'player_id': player_id,
            'player_name': player_name,
            'message': f'{player_name}さんは不正解でした。'
        })
    socketio.emit('update_players', game.players)

    if game.should_finish_question():
        finish_answer_phase()

@socketio.on('answer_timeout')
def handle_answer_timeout(data):
    player_id = data.get('player_id')
    if not is_valid_player_session(player_id):
        return
    step_id = data.get('step_id')
    success, gained_score, _ = game.process_timeout(player_id, step_id=step_id)
    if not success:
        return

    emit('answer_submitted_ack', {
        'is_correct': False,
        'is_timeout': True,
        'gained_score': gained_score,
        'score': game.players.get(player_id, {}).get('score', 0)
    })

    player_name = game.players.get(player_id, {}).get('name', 'プレイヤー')
    socketio.emit('player_incorrect_notice', {
        'player_id': player_id,
        'player_name': player_name,
        'message': f'{player_name}さんはタイムアウト（不正解）でした。'
    })
    socketio.emit('update_players', game.players)

    if game.should_finish_question():
        finish_answer_phase()

def finish_answer_phase():
    if not game.current_question or game.phase_finished:
        return
    game.phase_finished = True
    game.question_active = False

    answers_list = game.current_question.get('answers', [])
    official_ans = answers_list[0] if answers_list else ""

    if not game.submitted_answers:
        socketio.emit('question_through', {
            'message': '時間切れ（正解者なし）',
            'correct_answers': answers_list,
            'official_answer': official_ans,
            'correct_choice_index': game.correct_choice_index
        })
    else:
        socketio.emit('answer_result', {
            'submitted_answers': game.submitted_answers,
            'players': game.players,
            'correct_answers': answers_list,
            'official_answer': official_ans,
            'correct_choice_index': game.correct_choice_index
        })

    schedule_auto_advance()

def send_quiz_finished():
    global auto_advance_active, auto_advance_token, finish_after_current_q
    auto_advance_active = False
    finish_after_current_q = False
    auto_advance_token += 1

    rankings = []
    for pid, pdata in game.players.items():
        rankings.append({
            'player_id': pid,
            'name': pdata.get('name', 'ゲスト'),
            'score': max(0, pdata.get('score', 0)),
            'combo': pdata.get('combo', 0)
        })

    rankings.sort(key=lambda x: (x['score'], x['combo']), reverse=True)
    for i, rank_item in enumerate(rankings):
        rank_item['rank'] = i + 1

    socketio.emit('quiz_finished', {'rankings': rankings})

@socketio.on('finish_quiz')
def handle_finish_quiz():
    if not is_authenticated_host():
        emit('host_error', {'message': 'ホスト権限がありません。'})
        return
    global finish_after_current_q
    if game.question_active and not game.phase_finished:
        finish_after_current_q = True
        socketio.emit('last_question_notice', {
            'message': '現在の問題が最終問題になります。終了後にリザルトを表示します。'
        })
    else:
        send_quiz_finished()

@socketio.on('disconnect')
def handle_disconnect():
    global active_host_sid
    if request.sid == active_host_sid:
        active_host_sid = None
        socketio.emit('host_released_notice', {'message': 'ホスト権限が解放されました。'})
    game.disconnect_player(request.sid)
    socketio.emit('update_players', game.players)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)