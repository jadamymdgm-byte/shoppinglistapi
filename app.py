import streamlit as st
import sqlite3
import google.generativeai as genai
from PIL import Image
import json

# --- 1. Gemini API設定 ---
# Secretsから確実に読み込むための処理
if "GEMINI_API_KEY" not in st.secrets:
    st.error("⚠️ Secretsに 'GEMINI_API_KEY' が設定されていません。")
    st.info("Settings > Secrets に GEMINI_API_KEY = 'あなたのキー' を入力してください。")
    st.stop()

try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    # 最新の flash モデルを使用
    model = genai.GenerativeModel('gemini-2.0-flash')
except Exception as e:
    st.error(f"⚠️ APIの初期化に失敗しました: {e}")
    st.stop()

# --- 2. データベース処理 ---
def init_db():
    conn = sqlite3.connect('shopping_list.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS items 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, current INTEGER, needed INTEGER)''')
    conn.commit()
    return conn

conn = init_db()

def get_items():
    c = conn.cursor()
    c.execute("SELECT id, name, current, needed FROM items")
    return c.fetchall()

def add_item(name, current, needed):
    c = conn.cursor()
    c.execute("INSERT INTO items (name, current, needed) VALUES (?, ?, ?)", (name, current, needed))
    conn.commit()

def update_item_fields(item_id, current, needed):
    c = conn.cursor()
    c.execute("UPDATE items SET current = ?, needed = ? WHERE id = ?", (current, needed, item_id))
    conn.commit()

def delete_item(item_id):
    c = conn.cursor()
    c.execute("DELETE FROM items WHERE id = ?", (item_id,))
    conn.commit()

# --- 3. コールバック関数（即時反映用） ---
def buy_item(idx, curr, need):
    new_curr = min(curr + need, 15)
    update_item_fields(idx, new_curr, 0)
    st.session_state[f"c_{idx}"] = new_curr
    st.session_state[f"n_{idx}"] = 0

def update_qty(idx, curr_key, need_key):
    new_c = st.session_state[curr_key]
    new_n = st.session_state[need_key]
    update_item_fields(idx, new_c, new_n)

def delete_item_callback(idx):
    delete_item(idx)

# --- 4. UI設定 ---
st.set_page_config(page_title="AI買い物リスト", layout="centered")

st.markdown("""
<style>
.main .block-container {
    padding-top: 1.5rem;
    max-width: 500px;
}
.stButton > button {
    border-radius: 10px;
}
</style>
""", unsafe_allow_html=True)

st.title("🛒 AI買い物リスト")

# --- 5. 追加セクション ---
tab1, tab2 = st.tabs(["➕ 手動で追加", "📷 写真で追加"])

with tab1:
    with st.form("add_form", clear_on_submit=True):
        name_in = st.text_input("品名", placeholder="例：バナナ")
        curr_in = st.selectbox("在庫数", range(16), index=0)
        need_in = st.selectbox("必要数", range(16), index=1)
        if st.form_submit_button("リストに追加", use_container_width=True) and name_in:
            add_item(name_in, curr_in, need_in)
            st.rerun()

with tab2:
    st.write("写真を撮るとAIが食材を自動登録します")
    img_file = st.camera_input("カメラを起動")
    if not img_file:
        img_file = st.file_uploader("または画像を選択", type=['png', 'jpg', 'jpeg'])
    
    if img_file:
        img = Image.open(img_file)
        if st.button("✨ AIで分析して追加", type="primary", use_container_width=True):
            with st.spinner("AIが画像から食材を探しています..."):
                try:
                    # AIへの指示
                    prompt = "この画像にある食品をリストアップしてください。結果は必ず次のJSON形式で返してください: [{'item': '品名', 'quantity': 数量}]。数量は推測でOK。日本語で。"
                    response = model.generate_content([prompt, img], generation_config={"response_mime_type": "application/json"})
                    items_found = json.loads(response.text)
                    for d in items_found:
                        add_item(d['item'], d['quantity'], 1) # 見つけたものは在庫として、必要1で追加
                    st.success(f"{len(items_found)}個のアイテムを追加しました！")
                    st.rerun()
                except Exception as e:
                    st.error(f"分析に失敗しました。もう一度試してください。")

st.divider()

# --- 6. 献立提案 ---
if st.button("🍳 在庫から献立を提案してもらう", use_container_width=True):
    all_items = get_items()
    # 在庫がある、または買う予定の食材を抽出
    available = [i[1] for i in all_items if (i[2] > 0 or i[3] > 0)]
    
    if len(available) < 2:
        st.warning("献立を考えるには、食材が2種類以上必要です。")
    else:
        with st.spinner("Geminiがレシピを考案中..."):
            try:
                prompt = f"食材「{', '.join(available)}」を使った料理を3つ提案してください。形式は【料理名】■材料■作り方の順で、短く分かりやすくお願いします。"
                response = model.generate_content(prompt)
                st.markdown("### 🤖 AIのおすすめ献立")
                st.info(response.text)
            except Exception as e:
                st.error("提案中にエラーが発生しました。")

st.divider()

# --- 7. 買い物リスト表示（縦型カード） ---
st.subheader("現在のリスト")
items = get_items()

if not items:
    st.info("リストは空です")
else:
    for item in items:
        idx, name, curr, need = item
        is_buying = need > 0
        
        with st.container(border=True):
            st.caption("品名")
            if is_buying:
                st.markdown(f"### 🛒 {name}") # 買うものにアイコン
            else:
                st.markdown(f"### {name}")
            
            col_left, col_right = st.columns(2)
            with col_left:
                st.selectbox("在庫数", range(16), index=curr, key=f"c_{idx}", 
                             on_change=update_qty, args=(idx, f"c_{idx}", f"n_{idx}"))
            with col_right:
                st.selectbox("必要数", range(16), index=need, key=f"n_{idx}", 
                             on_change=update_qty, args=(idx, f"c_{idx}", f"n_{idx}"))
            
            st.write("")
            if is_buying:
                if st.button("購入完了", key=f"buy_{idx}", type="primary", use_container_width=True, 
                          on_click=buy_item, args=(idx, curr, need)):
                    pass # コールバックで処理
            else:
                if st.button("この項目を削除", key=f"del_{idx}", use_container_width=True, 
                          on_click=delete_item_callback, args=(idx,)):
                    pass
