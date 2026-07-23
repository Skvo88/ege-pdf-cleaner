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

batch_size = st.slider("📊 Выберите количество бланков в партии:", min_value=1, max_value=15, value=15)

if st.button(f"📥 Запросить партию ({batch_size} бланков)", type="primary", use_container_width=True):
    with st.spinner("Запрашиваем свободные бланки из Гугл Таблицы..."):
        try:
            res = requests.get(WEB_APP_URL, params={"action": "list", "variant": variant, "curator": curator, "limit": batch_size}, timeout=30)
            files = res.json() if res.status_code == 200 else []
        except Exception as e:
            st.error(f"Ошибка соединения с сервером: {e}")
            files = []

    if not files or len(files) == 0:
        st.warning("⚠️ Свободных работ для чистки по этому варианту нет! Пожалуйста, выберите другой вариант.")
    else:
        st.success(f"Найдено свободных бланков: {len(files)} шт. Формируем ZIP-архив...")

        # Скачиваем файлы параллельно для многократного ускорения
        from concurrent.futures import ThreadPoolExecutor

        def download_single_file(item):
            file_id = item["fileId"]
            filename = item["fileName"]
            try:
                res = requests.get(WEB_APP_URL, params={"action": "get_file", "fileId": file_id}, timeout=40)
                if res.status_code == 200:
                    return filename, base64.b64decode(res.text)
            except Exception as err:
                return filename, err
            return filename, None

        zip_buffer = io.BytesIO()

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(download_single_file, files))

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename, file_data in results:
                if isinstance(file_data, Exception):
                    st.error(f"Ошибка скачивания файла {filename}: {file_data}")
                elif file_data:
                    zf.writestr(filename, file_data)

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

            from concurrent.futures import ThreadPoolExecutor

            def upload_single_file(uploaded_file):
                filename = uploaded_file.name
                match = re.match(r"^ID_(\d+)__(.+)__испр\.pdf$", filename)
                if not match:
                    return filename, "Неверный формат названия. Имя должно быть вида ID_1234__ФИО__испр.pdf"

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
                    res = requests.post(WEB_APP_URL, json=payload, timeout=50)
                    if res.status_code == 200:
                        res_json = res.json()
                        if res_json.get("success"):
                            return filename, True
                        else:
                            return filename, res_json.get("error", "Ошибка обработки")
                    else:
                        return filename, "Ошибка сервера при обработке"
                except Exception as err:
                    return filename, f"Ошибка сети: {err}"

            with ThreadPoolExecutor(max_workers=3) as executor:
                results = list(executor.map(upload_single_file, uploaded_files))

            for filename, result in results:
                if result is True:
                    success_count += 1
                else:
                    st.error(f"❌ {filename}: {result}")

        if success_count > 0:
            st.balloons()
            st.success(f"🎉 Успешно загружено и обновлено в таблице: {success_count} из {total_files} бланков!\n\nВ столбце 'Кто чистил' записано: **{curator}**.")
