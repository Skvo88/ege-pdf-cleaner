import streamlit as st
import requests
import base64
import io
import zipfile
import re

# URL развернутого бэкенда Google Apps Script
WEB_APP_URL = "https://script.google.com/macros/s/AKfycbyagFr3GtUO3zQThO-tpst898De5MxIM3749q-in8rKK_0xHzNmtQpo6AYCMX8XULNj/exec"

# Список кураторов
CURATORS = [
    "Тизанова Амина",
    "Передирий Ксения",
    "Турушева Екатерина",
    "Кормина Алина",
    "Федченко Елизавета",
    "Александр (Админ)"
]

# Список вариантов КИМ
VARIANTS = [
    "Естественные науки",
    "Искусство",
    "Коммерческий банк"
]

# Настройки страницы Streamlit
st.set_page_config(page_title="Модуль чистки бланков", page_icon="🧹", layout="centered")

st.title("🧹 Модуль чистки бланков (ЕГЭ Обществознание)")
st.caption("Сервис автоматической выгрузки и загрузки бланков для кураторов")

# 1. Авторизация и выбор варианта
col1, col2 = st.columns(2)
with col1:
    curator = st.selectbox("👤 Кто вы (Куратор):", CURATORS)
with col2:
    variant = st.selectbox("📚 Вариант КИМ:", VARIANTS)

st.divider()

# 2. Блок скачивания бланков
st.subheader("1. Скачать партию бланков на чистку")

if st.button("📥 Запросить партию бланков (до 15 шт.)", type="primary", use_container_width=True):
    with st.spinner("Запрашиваем свободные бланки из Гугл Таблицы..."):
        try:
            res = requests.get(WEB_APP_URL, params={"action": "list", "variant": variant}, timeout=30)
            files = res.json() if res.status_code == 200 else []
        except Exception as e:
            st.error(f"Ошибка соединения с сервером: {e}")
            files = []

    if not files or len(files) == 0:
        st.warning("⚠️ Свободных работ для чистки по этому варианту нет! Пожалуйста, выберите другой вариант.")
    else:
        st.success(f"Найдено свободных бланков: {len(files)} шт. Формируем ZIP-архив...")
        
        # Скачиваем файлы и формируем ZIP в оперативной памяти
        zip_buffer = io.BytesIO()
        progress_bar = st.progress(0)
        
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for idx, item in enumerate(files):
                file_id = item["fileId"]
                filename = item["fileName"]
                
                try:
                    file_res = requests.get(WEB_APP_URL, params={"action": "get_file", "fileId": file_id}, timeout=30)
                    if file_res.status_code == 200:
                        file_bytes = base64.b64decode(file_res.text)
                        zf.writestr(filename, file_bytes)
                except Exception as err:
                    st.error(f"Ошибка скачивания файла {filename}: {err}")
                
                progress_bar.progress((idx + 1) / len(files))

        safe_variant = variant.replace(" ", "_")
        safe_curator = curator.replace(" ", "_")
        
        st.download_button(
            label=f"💾 Скачать ZIP-архив с {len(files)} бланками",
            data=zip_buffer.getvalue(),
            file_name=f"Чистка__{safe_variant}__{safe_curator}.zip",
            mime="application/zip",
            use_container_width=True
        )

st.divider()

# 3. Блок загрузки очищенных бланков обратно
st.subheader("2. Загрузить очищенные бланки обратно")

uploaded_files = st.file_uploader(
    "Перетащите сюда очищенные PDF-файлы (сохраняйте исходные названия файлов):",
    type=["pdf"],
    accept_multiple_files=True
)

if uploaded_files:
    if st.button("🚀 Отправить очищенные файлы в таблицу", type="primary", use_container_width=True):
        success_count = 0
        total_files = len(uploaded_files)
        
        with st.spinner("Сохранение файлов на Google Диск и обновление Гугл Таблицы..."):
            progress_bar = st.progress(0)
            
            for idx, uploaded_file in enumerate(uploaded_files):
                filename = uploaded_file.name
                
                # Парсим ID работы и ФИО из названия (ID_1234__ФИО__испр.pdf)
                match = re.match(r"^ID_(\d+)__(.+)__испр\.pdf$", filename)
                if not match:
                    st.error(f"❌ Файл '{filename}' пропущен: неверный формат названия. Имя должно быть вида ID_1234__ФИО__испр.pdf")
                    continue
                    
                work_id = match.group(1)
                fio = match.group(2).replace("_", " ")
                
                file_bytes = uploaded_file.read()
                base64_str = base64.b64encode(file_bytes).decode("utf-8")
                
                payload = {
                    "row": 0,
                    "id": work_id,
                    "fio": fio,
                    "cleanerName": curator,
                    "base64Data": base64_str
                }
                
                try:
                    res = requests.post(WEB_APP_URL, json=payload, timeout=40)
                    if res.status_code == 200 and res.json().get("success"):
                        success_count += 1
                    else:
                        st.error(f"❌ Ошибка сервера при обработке {filename}")
                except Exception as err:
                    st.error(f"❌ Ошибка сети при отправке {filename}: {err}")
                    
                progress_bar.progress((idx + 1) / total_files)

        if success_count > 0:
            st.balloons()
            st.success(f"🎉 Успешно загружено и обновлено в таблице: {success_count} из {total_files} бланков!\n\nВ столбце 'Кто чистил' записано: **{curator}**.")