import time
import random
from answer_checker import check_answer
from config import (
    FIRST_BUZZ_BONUS, SECOND_BUZZ_BONUS, THIRD_BUZZ_BONUS,
    TIME_LIMIT_CHOICE, TIME_LIMIT_MHY_PER_CHAR, TIME_LIMIT_TEXT,
    SCORE_CORRECT, SCORE_INCORRECT, COMBO_THRESHOLD, COMBO_BONUS
)

HIRAGANA_POOL = [chr(i) for i in range(0x3041, 0x3097)]
KATAKANA_POOL = [chr(i) for i in range(0x30A1, 0x30F7)]
DIGIT_POOL = list("0123456789")
ALPHABET_UPPER_POOL = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
ALPHABET_LOWER_POOL = list("abcdefghijklmnopqrstuvwxyz")

def get_character_pool(char):
    if not char:
        return HIRAGANA_POOL
    c = str(char)[0]
    code = ord(c)
    if 'a' <= c <= 'z':
        return ALPHABET_LOWER_POOL
    elif 'A' <= c <= 'Z':
        return ALPHABET_UPPER_POOL
    elif '0' <= c <= '9':
        return DIGIT_POOL
    elif 0x30A1 <= code <= 0x30F6:
        return KATAKANA_POOL
    elif 0x3041 <= code <= 0x3096:
        return HIRAGANA_POOL
    else:
        return HIRAGANA_POOL + KATAKANA_POOL + ALPHABET_LOWER_POOL + ALPHABET_UPPER_POOL + DIGIT_POOL

def parse_dummy_pool(dummy_setting, target_char):
    target_str = str(target_char)
    if not dummy_setting:
        return get_character_pool(target_str)
    
    setting_str = str(dummy_setting).replace("，", ",")
    tokens = [t.strip() for t in setting_str.split(",") if t.strip()]
    
    pool = []
    for token in tokens:
        if token in ("片仮名", "カタカナ"):
            pool.extend(KATAKANA_POOL)
        elif token in ("平仮名", "ひらがな"):
            pool.extend(HIRAGANA_POOL)
        elif token == "数字":
            pool.extend(DIGIT_POOL)
        elif token == "大文字":
            pool.extend(ALPHABET_UPPER_POOL)
        elif token == "小文字":
            pool.extend(ALPHABET_LOWER_POOL)
        else:
            pool.extend(list(token))
            
    seen = set()
    unique_pool = []
    for c in pool:
        if c not in seen:
            seen.add(c)
            unique_pool.append(c)
            
    return unique_pool if unique_pool else get_character_pool(target_str)

class GameManager:
    def __init__(self):
        self.players = {}
        self.kicked_player_ids = set()
        self.current_question = None
        self.buzz_order = []
        self.submitted_answers = {}
        self.active_answers = set()
        self.buzz_deadline = 0
        self.answer_deadline = 0
        
        self.question_start_time = 0
        self.char_speed = 0.08
        self.max_ans_duration = 0
        self.shuffled_choices = []
        self.correct_choice_index = 0
        self.correct_choice_text = ""

        self.mhy_target = ""
        self.mhy_progress = {}
        self.question_active = False
        self.current_q_token = 0
        self.round_q_count = 0
        self.phase_finished = False

    def reset_round(self):
        self.round_q_count = 0
        self.buzz_order = []
        self.submitted_answers = {}
        self.active_answers = set()
        self.mhy_progress = {}
        self.current_question = None
        self.question_active = False
        self.phase_finished = False

    def register_player(self, player_id, name, sid):
        if player_id in self.kicked_player_ids:
            return False
        
        # 1. 同じ player_id での復帰（離脱前のスコア・コンボを完全保持）
        if player_id in self.players:
            self.players[player_id]['sid'] = sid
            self.players[player_id]['is_connected'] = True
            if name:
                self.players[player_id]['name'] = name
            self.players[player_id]['score'] = max(0, self.players[player_id].get('score', 0))
            return True

        # 2. player_id が異なるが、離脱中(is_connected==False)で同一名前のプレイヤーが存在する場合の復元
        for existing_pid, pdata in list(self.players.items()):
            if not pdata.get('is_connected', True) and pdata.get('name') == name:
                self.players[player_id] = {
                    'name': name,
                    'score': max(0, pdata.get('score', 0)),
                    'combo': pdata.get('combo', 0),
                    'sid': sid,
                    'is_connected': True
                }
                del self.players[existing_pid]
                return True

        # 3. 完全新規プレイヤー
        self.players[player_id] = {
            'name': name,
            'score': 0,
            'combo': 0,
            'sid': sid,
            'is_connected': True
        }
        return True

    def kick_player(self, player_id):
        self.kicked_player_ids.add(player_id)
        if player_id in self.players:
            sid = self.players[player_id].get('sid')
            del self.players[player_id]
            return sid
        return None

    def start_question(self, qdata, char_speed=0.08, extra_buzz_sec=5.0):
        self.current_question = dict(qdata)
        
        q_text = ""
        for k in ['full_question', 'question', 'q_text', 'text', 'problem', 'content', 'statement', '問題文', '問題']:
            val = self.current_question.get(k)
            if val is not None and str(val).strip() != "":
                q_text = str(val)
                break

        self.current_question['question'] = q_text
        self.current_question['full_question'] = q_text
        self.current_question['q_text'] = q_text
        self.current_question['text'] = q_text
        self.current_question['problem'] = q_text

        self.buzz_order = []
        self.submitted_answers = {}
        self.active_answers = set()
        self.mhy_progress = {}
        self.char_speed = char_speed
        self.question_start_time = time.time()
        self.question_active = True
        self.phase_finished = False
        self.current_q_token += 1
        self.round_q_count += 1

        qtype = self.current_question.get('type')
        read_time = len(q_text) * char_speed
        total_buzz_window = read_time + extra_buzz_sec

        self.buzz_deadline = self.question_start_time + 2.2 + total_buzz_window
        self.answer_deadline = self.buzz_deadline

        if qtype == 'choice':
            orig_choices = list(self.current_question.get('choices', []))
            orig_ans_idx = self.current_question.get('answer_index', 0)
            self.correct_choice_text = str(orig_choices[orig_ans_idx]) if 0 <= orig_ans_idx < len(orig_choices) else ""
            self.shuffled_choices = orig_choices
            self.correct_choice_index = orig_ans_idx
            
            self.current_question['choices'] = orig_choices
            self.current_question['answer_index'] = orig_ans_idx
            ans_limit = TIME_LIMIT_CHOICE
        elif qtype == 'mhy':
            answers = self.current_question.get('answers', [])
            if answers and isinstance(answers, list):
                raw_target = str(answers[0])
            else:
                raw_target = str(self.current_question.get('answer', ''))
            
            cleaned_target = raw_target.replace(" ", "").replace(" ", "")
            self.mhy_target = cleaned_target
            ans_limit = len(self.mhy_target) * TIME_LIMIT_MHY_PER_CHAR if self.mhy_target else TIME_LIMIT_MHY_PER_CHAR
        else:
            ans_limit = TIME_LIMIT_TEXT

        official_ans = self.get_official_answer()
        self.current_question['official_answer'] = official_ans
        self.current_question['official_ans'] = official_ans
        self.current_question['answer_text'] = official_ans
        self.current_question['correct_answer'] = official_ans

        self.max_ans_duration = 2.2 + read_time + extra_buzz_sec + ans_limit

    def generate_mhy_choices(self, target_char):
        target_str = str(target_char)
        choices = [target_str]
        custom_dummies = self.current_question.get('dummy_chars') if self.current_question else None
        
        pool_chars = parse_dummy_pool(custom_dummies, target_str)
        pool = [str(c) for c in pool_chars if str(c) != target_str]
            
        if len(pool) < 3:
            backup_pool = HIRAGANA_POOL + KATAKANA_POOL + ALPHABET_LOWER_POOL + ALPHABET_UPPER_POOL + DIGIT_POOL
            additional = [str(c) for c in backup_pool if str(c) != target_str and str(c) not in pool]
            pool.extend(additional)
            
        selected_dummies = random.sample(pool, min(3, len(pool)))
        choices.extend(selected_dummies)
        random.shuffle(choices)
        return choices

    def process_buzz(self, player_id):
        if not self.current_question or self.phase_finished:
            return 999, 0, 10.0, "", [], 0, []

        now = time.time()
        if now > self.buzz_deadline + 3.0:
            return 999, 0, 10.0, "", [], 0, []

        if player_id in self.submitted_answers:
            if self.submitted_answers[player_id].get('is_timeout'):
                del self.submitted_answers[player_id]
            else:
                return 999, 0, 10.0, "", [], 0, []

        self.active_answers.add(player_id)

        if player_id in self.buzz_order:
            rank = self.buzz_order.index(player_id) + 1
        else:
            self.buzz_order.append(player_id)
            rank = len(self.buzz_order)

        if rank == 1:
            buzz_bonus = FIRST_BUZZ_BONUS
        elif rank == 2:
            buzz_bonus = SECOND_BUZZ_BONUS
        else:
            buzz_bonus = THIRD_BUZZ_BONUS

        q_text = self.current_question.get('full_question') or self.current_question.get('question', '')
        elapsed = max(0, now - (self.question_start_time + 2.2))
        char_count = max(1, min(len(q_text), int(elapsed / self.char_speed)))
        
        frozen_text = q_text[:char_count]

        qtype = self.current_question.get('type')
        mhy_choices = []
        player_choices = []
        step_id = 0

        if qtype == 'choice':
            limit_sec = TIME_LIMIT_CHOICE
            orig_choices = list(self.current_question.get('choices', []))
            shuffled = list(orig_choices)
            random.shuffle(shuffled)
            player_choices = shuffled
        elif qtype == 'mhy':
            limit_sec = TIME_LIMIT_MHY_PER_CHAR
            step_id = 1
            self.mhy_progress[player_id] = {'char_idx': 0, 'entered': '', 'step_id': step_id}
            if self.mhy_target:
                mhy_choices = self.generate_mhy_choices(self.mhy_target[0])
        else:
            limit_sec = TIME_LIMIT_TEXT

        self.answer_deadline = now + limit_sec + 2.0

        return rank, buzz_bonus, limit_sec, frozen_text, mhy_choices, step_id, player_choices

    def process_mhy_step(self, player_id, char):
        if (player_id in self.submitted_answers and not self.submitted_answers[player_id].get('is_timeout')) or player_id not in self.mhy_progress:
            return False, False, False, "", [], 0, 0, False, 0

        prog = self.mhy_progress[player_id]
        idx = prog['char_idx']

        if idx < len(self.mhy_target):
            target_char = self.mhy_target[idx]
            if str(char) == target_char:
                prog['entered'] += target_char
                prog['char_idx'] += 1
                prog['step_id'] += 1

                if prog['char_idx'] >= len(self.mhy_target):
                    success, is_correct, gained, all_completed = self.process_answer(player_id, prog['entered'])
                    return True, True, True, prog['entered'], [], 0, gained, all_completed, prog['step_id']
                else:
                    next_char = self.mhy_target[prog['char_idx']]
                    next_choices = self.generate_mhy_choices(next_char)
                    self.answer_deadline = time.time() + TIME_LIMIT_MHY_PER_CHAR + 2.0
                    return True, False, True, prog['entered'], next_choices, TIME_LIMIT_MHY_PER_CHAR, 0, False, prog['step_id']

        wrong_ans = prog['entered'] + str(char)
        success, is_correct, gained, all_completed = self.process_answer(player_id, wrong_ans)
        return True, True, False, wrong_ans, [], 0, gained, all_completed, prog['step_id']

    def should_finish_question(self):
        if self.phase_finished:
            return False

        online_players = [pid for pid, p in self.players.items() if p.get('is_connected', True)]
        if online_players and len(self.submitted_answers) >= len(online_players):
            return True

        now = time.time()
        if len(self.active_answers) > 0:
            if now < self.answer_deadline:
                return False
            else:
                return True

        if now >= self.buzz_deadline + 1.0:
            return True

        return False

    def get_official_answer(self):
        if not self.current_question:
            return ""
        qtype = self.current_question.get('type')
        if qtype == 'choice':
            if hasattr(self, 'correct_choice_text') and self.correct_choice_text:
                return self.correct_choice_text
            choices = self.current_question.get('choices', [])
            idx = self.correct_choice_index
            if 0 <= idx < len(choices):
                return choices[idx]
            return ""
        elif qtype == 'mhy':
            return self.mhy_target
        else:
            answers = self.current_question.get('answers', [])
            if answers:
                return " / ".join([str(a) for a in answers])
            return str(self.current_question.get('answer', ''))

    def get_question_result(self):
        if not self.current_question:
            return {}
        full_q = self.current_question.get('full_question') or self.current_question.get('question', '')
        official_ans = self.get_official_answer()
        res = dict(self.current_question)
        res.update({
            'question': full_q,
            'full_question': full_q,
            'q_text': full_q,
            'text': full_q,
            'problem': full_q,
            'type': self.current_question.get('type'),
            'official_answer': official_ans,
            'official_ans': official_ans,
            'answer': official_ans,
            'answer_text': official_ans,
            'correct_answer': official_ans,
            'answers': self.current_question.get('answers', []),
            'submitted_answers': self.submitted_answers
        })
        return res

    def get_current_question(self):
        return self.get_question_result()

    def process_answer(self, player_id, answer):
        self.active_answers.discard(player_id)

        if player_id in self.submitted_answers and not self.submitted_answers[player_id].get('is_timeout'):
            return False, "すでに解答済みです", 0, False

        qtype = self.current_question.get('type') if self.current_question else 'text'
        is_correct = False

        if qtype == 'choice':
            correct_text = getattr(self, 'correct_choice_text', '')
            if not correct_text:
                choices = self.current_question.get('choices', [])
                if 0 <= self.correct_choice_index < len(choices):
                    correct_text = choices[self.correct_choice_index]
            
            user_ans_str = str(answer).strip()
            is_correct = (user_ans_str == correct_text or check_answer(user_ans_str, [correct_text]))

        elif qtype in ('text', 'mhy'):
            answers = self.current_question.get('answers', [])
            if not answers and 'answer' in self.current_question:
                answers = [self.current_question['answer']]
            is_correct = check_answer(str(answer), answers)

        rank = self.buzz_order.index(player_id) + 1 if player_id in self.buzz_order else 999
        buzz_bonus = FIRST_BUZZ_BONUS if rank == 1 else (SECOND_BUZZ_BONUS if rank == 2 else THIRD_BUZZ_BONUS)

        if player_id not in self.players:
            self.players[player_id] = {'name': 'ゲスト', 'score': 0, 'combo': 0, 'sid': None, 'is_connected': True}
        pinfo = self.players[player_id]

        gained_score = 0

        if is_correct:
            pinfo['combo'] += 1
            combo_bonus = COMBO_BONUS if pinfo['combo'] >= COMBO_THRESHOLD else 0
            gained_score = SCORE_CORRECT + buzz_bonus + combo_bonus
            pinfo['score'] = max(0, pinfo.get('score', 0) + gained_score)
        else:
            pinfo['combo'] = 0
            gained_score = SCORE_INCORRECT
            pinfo['score'] = max(0, pinfo.get('score', 0) + gained_score)

        full_q = self.current_question.get('full_question') or self.current_question.get('question', '') if self.current_question else ''
        official_ans = self.get_official_answer()

        self.submitted_answers[player_id] = {
            'answer': answer,
            'is_correct': is_correct,
            'is_timeout': False,
            'rank': rank,
            'buzz_bonus': buzz_bonus if is_correct else 0,
            'gained_score': gained_score,
            'score': pinfo['score'],
            'combo': pinfo['combo'],
            'full_question': full_q,
            'question': full_q,
            'q_text': full_q,
            'text': full_q,
            'problem': full_q,
            'official_answer': official_ans,
            'official_ans': official_ans,
            'answer_text': official_ans,
            'correct_answer': official_ans
        }

        return True, is_correct, gained_score, self.should_finish_question()

    def process_timeout(self, player_id, step_id=None):
        if player_id in self.active_answers and step_id is None:
            return False, 0, False

        self.active_answers.discard(player_id)

        if player_id in self.submitted_answers and not self.submitted_answers[player_id].get('is_timeout'):
            return False, 0, False

        if step_id is not None and player_id in self.mhy_progress:
            current_step = self.mhy_progress[player_id].get('step_id', 0)
            if step_id != current_step:
                return False, 0, False

        rank = self.buzz_order.index(player_id) + 1 if player_id in self.buzz_order else 999
        
        if player_id not in self.players:
            self.players[player_id] = {'name': 'ゲスト', 'score': 0, 'combo': 0, 'sid': None, 'is_connected': True}
        pinfo = self.players[player_id]
        
        pinfo['combo'] = 0
        gained_score = SCORE_INCORRECT
        pinfo['score'] = max(0, pinfo.get('score', 0) + gained_score)

        entered_text = ""
        if player_id in self.mhy_progress:
            entered_text = self.mhy_progress[player_id].get('entered', '')

        full_q = self.current_question.get('full_question') or self.current_question.get('question', '') if self.current_question else ''
        official_ans = self.get_official_answer()

        self.submitted_answers[player_id] = {
            'answer': (entered_text + "（時間切れ）") if entered_text else "（時間切れ）",
            'is_correct': False,
            'is_timeout': True,
            'rank': rank,
            'buzz_bonus': 0,
            'gained_score': gained_score,
            'score': pinfo['score'],
            'combo': pinfo['combo'],
            'full_question': full_q,
            'question': full_q,
            'q_text': full_q,
            'text': full_q,
            'problem': full_q,
            'official_answer': official_ans,
            'official_ans': official_ans,
            'answer_text': official_ans,
            'correct_answer': official_ans
        }

        return True, gained_score, self.should_finish_question()

    def disconnect_player(self, sid):
        for pid, pdata in self.players.items():
            if pdata.get('sid') == sid:
                pdata['is_connected'] = False
                pdata['sid'] = None
                return pid
        return None