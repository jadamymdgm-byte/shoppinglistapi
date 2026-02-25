import streamlit as st
import sqlite3
import google.generativeai as genai
from PIL import Image
import json

# --- 1. Gemini API設定 ---
# Streamlit Cloudの「Secrets」に設定したキーを使用します
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=GEMINI_API_KEY)
    # 高速・高精度な flash モデルを使用
    model = genai.GenerativeModel('gemini-2.0-flash')
except Exception:
    st.error("⚠️ StreamlitのSecretsに 'GEMINI_API_KEY' が設定されていないか、無効です。")
    st.info("設定方法：Streamlit Cloudのアプリ管理画面 ＞ Settings ＞ Secrets に「GEMINI_API_KEY = 'あなたのキー'」を貼り付けてください。")
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

# --- 3. コールバック関数（即時反映） ---
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

# スマホ向けスタイル調整
st.markdown("""
<style>
.main .block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
    max-width: 500px;
}
.stButton > button {
    border-radius: 8px;
}
</style>
""", unsafe_allow_html=True)

st.title("🛒 AI買い物リスト")

# --- 5. 品物の追加セクション ---
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
    st.write("冷蔵庫などの写真を撮るとAIが在庫を読み取ります")
    img_file = st.camera_input("撮影する")
    if not img_file:
        img_file = st.file_uploader("または画像を選択", type=['png', 'jpg', 'jpeg'])
    
    if img_file:
        img = Image.open(img_file)
        if st.button("✨ AIで画像を分析して追加", type="primary", use_container_width=True):
            with st.spinner("AIが分析中..."):
                try:
                    prompt = "この画像から食品を抽出し、JSON形式でリストアップしてください。形式: [{'item': '品名', 'quantity': 数量}]。数量は推測で構いません。日本語で回答してください。"
                    response = model.generate_content([prompt, img], generation_config={"response_mime_type": "application/json"})
                    data = json.loads(response.text)
                    for d in data:
                        # 見つけたものは在庫として、必要数は1でとりあえず追加
                        add_item(d['item'], d['quantity'], 1)
                    st.success("分析完了！リストに追加しました。")
                    st.rerun()
                except Exception as e:
                    st.error(f"分析に失敗しました。もう一度試してください。")

st.divider()

# --- 6. 献立提案セクション ---
if st.button("🍳 在庫と買い物予定で献立を考える", use_container_width=True):
    items = get_items()
    # 在庫または必要数が1以上のものを抽出
    ingredients = list(set([item[1] for item in items if (item[2] > 0 or item[3] > 0)]))
    
    if len(ingredients) < 2:
        st.warning("献立を提案するには、2種類以上の食材が必要です。")
    else:
        with st.spinner("Geminiが献立を考案中..."):
            try:
                prompt = f"現在、家に「{', '.join(ingredients)}」があります。これらで作れる料理を3つ提案してください。形式は【レシピ名】■材料■作り方でお願いします。"
                response = model.generate_content(prompt)
                st.markdown("### 🤖 AIのおすすめ献立")
                st.info(response.text)
            except Exception as e:
                st.error("提案に失敗しました。")

st.divider()

# --- 7. 買い物リスト表示（縦型カードレイアウト） ---
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
                st.markdown(f"### 🛒 {name}")
            else:
                st.markdown(f"### {name}")
            
            # 在庫と必要数の設定
            col_a, col_b = st.columns(2)
            with col_a:
                st.selectbox("在庫数", range(16), index=curr, key=f"c_{idx}", 
                             on_change=update_qty, args=(idx, f"c_{idx}", f"n_{idx}"))
            with col_b:
                st.selectbox("必要数", range(16), index=need, key=f"n_{idx}", 
                             on_change=update_qty, args=(idx, f"c_{idx}", f"n_{idx}"))
            
            st.write("")
            if is_buying:
                # 購入ボタン
                st.button("購入", key=f"buy_{idx}", type="primary", use_container_width=True, 
                          on_click=buy_item, args=(idx, curr, need))
            else:
                # 削除ボタン
                st.button("削除", key=f"del_{idx}", use_container_width=True, 
                          on_click=delete_item_callback, args=(idx,))
