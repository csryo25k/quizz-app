import os
import re
import openpyxl
from openpyxl.utils import column_index_from_string

def parse_choice_answer_index(cell_val, choices):
    """
    セル指定 (C, D, E, F, C列, D列, 1, 2, 3, 4 等) やテキストから
    0-based インデックス (0, 1, 2, 3) を特定する
    """
    if cell_val is None:
        return 0
    
    val_str = str(cell_val).strip()
    
    if val_str.startswith("="):
        val_str = val_str.replace("=", "").strip()
        match = re.match(r"^([A-Za-z]+)", val_str)
        if match:
            val_str = match.group(1)

    val_upper = val_str.upper()
    
    col_map = {
        "C": 0, "D": 1, "E": 2, "F": 3,
        "C列": 0, "D列": 1, "E列": 2, "F列": 3,
        "1": 0, "2": 1, "3": 2, "4": 3,
        "0": 0
    }
    if val_upper in col_map:
        return col_map[val_upper]
    
    if len(val_upper) >= 2 and val_upper[0] in col_map:
        return col_map[val_upper[0]]
        
    for idx, c in enumerate(choices):
        if str(c).strip().lower() == val_str.lower():
            return idx
            
    return 0

def get_cell_value_smart(ws_data, ws_formula, row_idx, col_idx):
    """
    計算後の値(data_only=True)と数式(data_only=False)の双方から値を解決する
    col_idx: 1-based (A=1, B=2, C=3, ..., H=8, I=9)
    """
    # 1. まず計算後の値を取得
    val_data = ws_data.cell(row=row_idx, column=col_idx).value
    if val_data is not None and str(val_data).strip() != "":
        return val_data

    # 2. 計算後の値がない(None)場合、数式文字列を取得して解析
    val_formula = ws_formula.cell(row=row_idx, column=col_idx).value
    if val_formula is None:
        return None

    val_str = str(val_formula).strip()
    if val_str.startswith("="):
        clean = val_str[1:].strip().upper()
        # 例: "=C2" や "=D5" のようなセル参照の場合
        match_cell = re.match(r"^([A-Z]+)(\d+)$", clean)
        if match_cell:
            col_letter = match_cell.group(1)
            target_row = int(match_cell.group(2))
            target_col = column_index_from_string(col_letter)
            # 参照先セルの値を取得
            target_val = ws_data.cell(row=target_row, column=target_col).value
            if target_val is None:
                target_val = ws_formula.cell(row=target_row, column=target_col).value
            return target_val if target_val is not None else col_letter

        # 例: "=C" や "=C列" のような列指定の場合
        match_col = re.match(r"^([A-Z]+)", clean)
        if match_col:
            return match_col.group(1)

    return val_str

def load_questions(filepath: str, difficulty: str = "all") -> list:
    if not os.path.exists(filepath):
        print(f"[Warning] Questions file not found at {filepath}")
        return []

    try:
        # 計算結果用と数式解析用の2つのモードでワークブックを開く
        wb_data = openpyxl.load_workbook(filepath, data_only=True)
        wb_formula = openpyxl.load_workbook(filepath, data_only=False)
    except Exception as e:
        print(f"[Warning] Failed to open Excel file: {e}")
        return []

    all_levels = ["easy", "normal-", "normal", "normal+", "difficult"]
    target_sheets = []

    if difficulty in all_levels:
        if difficulty in wb_data.sheetnames:
            target_sheets = [difficulty]
    else:
        for sheet_name in all_levels:
            if sheet_name in wb_data.sheetnames:
                target_sheets.append(sheet_name)
        if not target_sheets:
            target_sheets = wb_data.sheetnames

    questions = []
    global_id = 1

    for sheet_name in target_sheets:
        ws_data = wb_data[sheet_name]
        ws_formula = wb_formula[sheet_name]

        max_r = ws_data.max_row
        for row_idx in range(2, max_r + 1):
            q_text = ws_data.cell(row=row_idx, column=1).value  # A列
            if not q_text or str(q_text).strip() == "":
                continue

            q_type_val = ws_data.cell(row=row_idx, column=2).value  # B列
            q_type = str(q_type_val).strip().lower() if q_type_val is not None else "text"
            if q_type not in ("mhy", "choice", "text"):
                q_type = "text"

            item = {
                "id": global_id,
                "sheet": sheet_name,
                "difficulty": sheet_name,
                "question": str(q_text).strip(),
                "type": q_type
            }
            global_id += 1

            # I列(9) -> H列(8) の順で優先読み込み
            ans_cell_val = get_cell_value_smart(ws_data, ws_formula, row_idx, 9)
            if ans_cell_val is None or str(ans_cell_val).strip() == "":
                ans_cell_val = get_cell_value_smart(ws_data, ws_formula, row_idx, 8)

            print(f"[DEBUG] シート:{sheet_name} 行:{row_idx} | 最終判定正解値: {ans_cell_val}")

            if q_type == "choice":
                choices = []
                for col_i in range(3, 7):  # C～F列 (3～6)
                    val = get_cell_value_smart(ws_data, ws_formula, row_idx, col_i)
                    choices.append(str(val).strip() if val is not None else "")
                
                if not any(choices):
                    choices = ["選択肢1", "選択肢2", "選択肢3", "選択肢4"]

                ans_idx = parse_choice_answer_index(ans_cell_val, choices)
                item["choices"] = choices
                item["answer_index"] = ans_idx

            elif q_type == "mhy":
                g_val = get_cell_value_smart(ws_data, ws_formula, row_idx, 7)  # G列
                if g_val:
                    item["dummy_chars"] = str(g_val).strip()

                ans = str(ans_cell_val).strip() if ans_cell_val is not None else ""
                item["answers"] = [ans] if ans else ["正解"]

            elif q_type == "text":
                val_str = str(ans_cell_val).replace("，", ",") if ans_cell_val is not None else ""
                raw_answers = [a.strip() for a in val_str.split(",") if a.strip()]
                item["answers"] = raw_answers if raw_answers else ["正解"]

            questions.append(item)

    return questions