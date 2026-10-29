import os

# ディレクトリパス設定（Render・ローカル両対応）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_FILE = os.path.join(BASE_DIR, "questions", "question.xlsx")
if not os.path.exists(QUESTIONS_FILE):
    # ルート直下にquestionsがある場合のフォールバック
    QUESTIONS_FILE = os.path.join(os.path.dirname(BASE_DIR), "questions", "question.xlsx")

# 得点仕様
SCORE_CORRECT = 10
SCORE_INCORRECT = -10
FIRST_BUZZ_BONUS = 10
SECOND_BUZZ_BONUS = 5
THIRD_BUZZ_BONUS = 0

COMBO_THRESHOLD = 3  # 3問以上連続正解でボーナス発動
COMBO_BONUS = 5      # 3問目以降の正解ごとの追加ボーナス

# 回答制限時間（秒）
TIME_LIMIT_CHOICE = 3.0        # 4択早押し: 3秒
TIME_LIMIT_MHY_PER_CHAR = 3.0  # 文字選択式: 各文字3秒
TIME_LIMIT_TEXT = 10.0         # テキスト式: 10秒
TIME_LIMIT_THROUGH = 5.0      # 全文表示後の早押し受付時間: 5秒

# 自動進行設定
AUTO_ADVANCE_DELAY = 4.0     # 解答発表後の自動次問題移行間隔（秒）

# 難易度定義（5段階）
DIFFICULTY_LEVELS = ["easy", "normal-", "normal", "normal+", "difficult"]

# 難易度別の出題割合（%）設定
DIFFICULTY_RATES = {
    "all": [10, 15, 40, 25, 10],        # 全選択
    "easy": [50, 30, 15, 5, 0],         # 簡単
    "normal-": [20, 40, 25, 10, 5],     # 普通-
    "normal": [0, 15, 45, 30, 10],       # 普通
    "normal+": [0, 5, 35, 45, 15],      # 普通＋
    "difficult": [0, 0, 10, 40, 50]     # 難しい
}