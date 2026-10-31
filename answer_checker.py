import re
import unicodedata

try:
    import jaconv
except ImportError:
    jaconv = None

def katakana_to_hiragana(text: str) -> str:
    """jaconv が利用可能ならカタカナをひらがなに変換、なければ代替処理"""
    if jaconv:
        return jaconv.kata2hira(text)
    res = []
    for char in text:
        code = ord(char)
        if 0x30A1 <= code <= 0x30F6:
            res.append(chr(code - 0x60))
        else:
            res.append(char)
    return "".join(res)

def normalize_text(text: str) -> str:
    """
    Unicode正規化(NFKC)、小文字化、カタカナ->ひらがな変換、
    記号・スペース除去を行う（「々」などの踊り字やカタカナ範囲も保護）
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", str(text))
    text = text.lower()
    text = katakana_to_hiragana(text)
    text = re.sub(r"[^\w\u3040-\u309f\u30a0-\u30ff\u4e00-\u9faf\u30fc\u3005]", "", text)
    return text

def check_answer(user_answer: str, correct_answers) -> bool:
    """
    ユーザーの回答が正解リストのいずれかと揺れを吸収して一致するか判定
    """
    norm_user = normalize_text(user_answer)
    if not norm_user:
        return False
    
    if isinstance(correct_answers, (str, int, float)):
        correct_answers = [str(correct_answers)]
    
    for ans in correct_answers:
        norm_ans = normalize_text(str(ans))
        if norm_user == norm_ans:
            return True
    return False