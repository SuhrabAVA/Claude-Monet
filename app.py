import os
from flask import Flask, render_template, request, redirect, url_for, flash, abort, session
from werkzeug.utils import secure_filename
import re
import json
import sqlite3
from pathlib import Path
from datetime import datetime

from supabase_service import (
    supabase_enabled,
    list_categories,
    list_menu_items,
    upsert_category,
    insert_menu_item,
    get_menu_item,
    insert_booking,
    insert_booking_items,
    list_bookings,
    get_booking,
    list_booking_items,
)

app = Flask(__name__)
app.secret_key = "change_this_secret_key"

# If SUPABASE_URL + SUPABASE_ANON_KEY are provided, the app uses Supabase (Postgres).
USE_SUPABASE = supabase_enabled()

DB_PATH = Path(__file__).with_name("bookings.sqlite3")
MENU_DATA_PATH = Path(__file__).with_name("menu_data.json")  # fallback (when Supabase is not configured)
UPLOAD_DIR = Path(__file__).with_name("static") / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _table_columns(con: sqlite3.Connection, table: str) -> set:
    cols = set()
    cur = con.execute(f"PRAGMA table_info({table})")
    for row in cur.fetchall():
        # row: (cid, name, type, notnull, dflt_value, pk)
        cols.add(row[1])
    return cols


def _ensure_column(con: sqlite3.Connection, table: str, col: str, col_sql: str) -> None:
    cols = _table_columns(con, table)
    if col not in cols:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_sql}")


def init_db():
    """
    Создаёт таблицу бронирований (если её нет) и при необходимости
    добавляет новые колонки в уже существующую таблицу.
    """
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                guests INTEGER NOT NULL,
                comment TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # миграции (безопасно для уже существующей базы)
        _ensure_column(con, "bookings", "email", "TEXT")
        _ensure_column(con, "bookings", "notes", "TEXT")
        _ensure_column(con, "bookings", "cart_items", "TEXT")   # JSON строка
        _ensure_column(con, "bookings", "cart_total", "TEXT")   # "$48" и т.п.

        con.commit()


# ======= ДАННЫЕ МЕНЮ =======
# По умолчанию меню хранится в коде, но админка добавляет новые позиции
# в menu_data.json (чтобы они сохранялись между перезапусками).

DEFAULT_CATEGORIES = [
    {"slug": "zakuski", "label": "Закуски"},
    {"slug": "mains", "label": "Основные блюда"},
    {"slug": "desserts", "label": "Десерты"},
    {"slug": "drinks", "label": "Напитки"},
]

DEFAULT_MENU_ITEMS = [
    # Закуски
    {
        "id": 1,
        "cat": "zakuski",
        "title": "Escargots de Bourgogne",
        "price": "₸18",
        "desc": "Бургундские улитки с чесночным травяным маслом и свежей петрушкой",
        "img": "img/menu/zakuski_1.jpg",
    },
    {
        "id": 2,
        "cat": "zakuski",
        "title": "Foie Gras Terrine",
        "price": "₸24",
        "desc": "Террин из утиной печени с инжирным конфитюром и поджаренной бриошью",
        "img": "img/menu/zakuski_2.jpg",
        "ingredients": ["утиная печень", "инжир", "бриошь", "портвейн", "коньяк"],
        "allergens": ["Молочные продукты", "Глютен", "Алкоголь"],
    },
    {
        "id": 3,
        "cat": "zakuski",
        "title": "Soupe à l'Oignon",
        "price": "₸14",
        "desc": "Классический луковый суп с сыром Грюйер и гренками из закваски",
        "img": "img/menu/zakuski_3.jpg",
    },
    {
        "id": 4,
        "cat": "zakuski",
        "title": "Huîtres",
        "price": "₸22",
        "desc": "Свежие устрицы с соусом миньонет и лимоном",
        "img": "img/menu/zakuski_4.jpg",
    },

    # Основные
    {
        "id": 5,
        "cat": "mains",
        "title": "Coq au Vin",
        "price": "$38",
        "desc": "Тушеная курица в красном вине с жемчужным луком и грибами",
        "img": "img/menu/mains_1.jpg",
    },
    {
        "id": 6,
        "cat": "mains",
        "title": "Boeuf Bourguignon",
        "price": "₸42",
        "desc": "Медленно тушеная говядина в бургундском винном соусе с корнеплодами",
        "img": "img/menu/mains_2.jpg",
    },
    {
        "id": 7,
        "cat": "mains",
        "title": "Sole Meunière",
        "price": "$46",
        "desc": "Жареная камбала со сливочным маслом, лимоном и каперсами",
        "img": "img/menu/mains_3.jpg",
    },

    # Десерты
    {
        "id": 8,
        "cat": "desserts",
        "title": "Crème Brûlée",
        "price": "₸12",
        "desc": "Классический ванильный крем с карамелизированной сахарной корочкой",
        "img": "img/menu/desserts_1.jpg",
    },
    {
        "id": 9,
        "cat": "desserts",
        "title": "Tarte Tatin",
        "price": "₸14",
        "desc": "Перевернутый карамелизированный яблочный тарт с ванильным мороженым",
        "img": "img/menu/desserts_2.jpg",
    },
    {
        "id": 10,
        "cat": "desserts",
        "title": "Soufflé au Chocolat",
        "price": "₸16",
        "desc": "Легкое шоколадное суфле (время приготовления 20 мин)",
        "img": "img/menu/desserts_3.jpg",
    },
    {
        "id": 11,
        "cat": "desserts",
        "title": "Profiteroles",
        "price": "₸13",
        "desc": "Заварные пирожные с ванильным мороженым и теплым шоколадным соусом",
        "img": "img/menu/desserts_4.jpg",
    },

    # Напитки (пример)
    {
        "id": 12,
        "cat": "drinks",
        "title": "Chardonnay (glass)",
        "price": "₸11",
        "desc": "Сухое белое вино, бокал",
        "img": "img/menu/drinks_1.jpg",
    },
    {
        "id": 13,
        "cat": "drinks",
        "title": "Bordeaux Rouge (glass)",
        "price": "₸12",
        "desc": "Красное вино, бокал",
        "img": "img/menu/drinks_2.jpg",
    },
    {
        "id": 14,
        "cat": "drinks",
        "title": "Espresso",
        "price": "₸4",
        "desc": "Классический эспрессо",
        "img": "img/menu/drinks_3.jpg",
    },
    {
        "id": 15,
        "cat": "drinks",
        "title": "Signature Cocktail",
        "price": "₸14",
        "desc": "Авторский коктейль бармена",
        "img": "img/menu/drinks_4.jpg",
    },
]


def _slugify(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9\s_-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "category"


def load_menu_data() -> tuple[list[dict], list[dict]]:
    """Fallback меню (локально).

    Если Supabase настроен — меню берём из Supabase, а JSON используется только
    когда Supabase не подключен.
    """
    if USE_SUPABASE:
        return list(DEFAULT_CATEGORIES), list(DEFAULT_MENU_ITEMS)

    if MENU_DATA_PATH.exists():
        try:
            data = json.loads(MENU_DATA_PATH.read_text(encoding="utf-8"))
            cats = data.get("categories") or []
            items = data.get("items") or []
            # Если categories является списком, считаем данные валидными даже при пустом items.
            # Это позволяет держать меню пустым, не возвращаясь к демонстрационным блюдам.
            if isinstance(cats, list) and cats:
                # items может быть пустым списком — это тоже валидно
                return cats, items if isinstance(items, list) else []
        except Exception:
            pass

    # если файла нет или повреждён, сохраняем дефолтные категории (без позиций)
    save_menu_data(DEFAULT_CATEGORIES, [])
    return list(DEFAULT_CATEGORIES), []


def save_menu_data(categories: list[dict], items: list[dict]) -> None:
    if USE_SUPABASE:
        return
    payload = {"categories": categories, "items": items}
    MENU_DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------
#    MENU DATA (Supabase)
# ---------------------------

_MENU_CACHE: dict = {"ts": 0.0, "categories": [], "items": []}
_MENU_CACHE_SECONDS = 30


def _price_cents_from_str(price_str: str) -> int:
    return int(round(parse_price_to_float(price_str) * 100))


def _split_csv(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    return [x.strip() for x in text.split(",") if x.strip()]


def ensure_supabase_seed() -> None:
    """Заполняет Supabase дефолтными категориями/меню, если таблицы пустые."""
    if not USE_SUPABASE:
        return

    try:
        cats = list_categories()
        if not cats:
            for c in DEFAULT_CATEGORIES:
                upsert_category(c["slug"], c["label"])

        items = list_menu_items()
        # Не заполняем базу демонстрационными блюдами. Если позиций нет, администратор
        # добавит их вручную через интерфейс. Поэтому пропускаем загрузку DEFAULT_MENU_ITEMS.
        _ = items  # nothing to seed
    except Exception:
        # Если Supabase не доступен, просто молча оставим дефолт на страницах
        return


def get_menu_data(force: bool = False) -> tuple[list[dict], list[dict]]:
    """Возвращает (categories, items). При Supabase — тянет из БД + кеш на 30 секунд."""
    global _MENU_CACHE

    if not USE_SUPABASE:
        return load_menu_data()

    now_ts = datetime.utcnow().timestamp()
    if (not force) and _MENU_CACHE["categories"] and (now_ts - _MENU_CACHE["ts"] < _MENU_CACHE_SECONDS):
        return _MENU_CACHE["categories"], _MENU_CACHE["items"]

    try:
        cats_raw = list_categories()
        items_raw = list_menu_items()
        if not cats_raw:
            ensure_supabase_seed()
            cats_raw = list_categories()
            items_raw = list_menu_items()

        categories = [{"slug": c.get("slug"), "label": c.get("label")} for c in (cats_raw or [])]

        items: list[dict] = []
        for r in (items_raw or []):
            price_cents = int(r.get("price_cents") or 0)
            items.append({
                "id": r.get("id"),
                "cat": r.get("category_slug"),
                "title": r.get("title") or "",
                "price_cents": price_cents,
                "price": money(price_cents),
                "desc": r.get("description") or "",
                "img": (r.get("image_path") or "img/placeholder.jpg").lstrip("/"),
                "ingredients": _split_csv(r.get("ingredients") or ""),
                "allergens": _split_csv(r.get("allergens") or ""),
                "wine_title": r.get("wine_title") or "",
                "wine_text": r.get("wine_text") or "",
            })

        _MENU_CACHE = {"ts": now_ts, "categories": categories, "items": items}
        return categories, items
    except Exception:
        # тихий fallback
        return list(DEFAULT_CATEGORIES), list(DEFAULT_MENU_ITEMS)


def group_menu_items():
    categories, items = get_menu_data()
    grouped = {c["slug"]: [] for c in categories}
    for item in items:
        grouped.setdefault(item["cat"], []).append(item)
    return grouped


def get_item_by_id(item_id: int):
    _, items = get_menu_data()
    for x in items:
        if int(x.get("id") or 0) == int(item_id):
            return x
    # if Supabase enabled, try direct fetch
    if USE_SUPABASE:
        try:
            r = get_menu_item(int(item_id))
            if r:
                price_cents = int(r.get("price_cents") or 0)
                return {
                    "id": r.get("id"),
                    "cat": r.get("category_slug"),
                    "title": r.get("title") or "",
                    "price_cents": price_cents,
                    "price": money(price_cents),
                    "desc": r.get("description") or "",
                    "img": (r.get("image_path") or "img/placeholder.jpg").lstrip("/"),
                    "ingredients": _split_csv(r.get("ingredients") or ""),
                    "allergens": _split_csv(r.get("allergens") or ""),
                    "wine_title": r.get("wine_title") or "",
                    "wine_text": r.get("wine_text") or "",
                }
        except Exception:
            pass
    return None


def parse_price_to_float(price_str: str) -> float:
    # "$24" / "24" / "24.50" / "24,50" -> 24.5
    if not price_str:
        return 0.0
    s = price_str.strip().replace(",", ".")
    s = re.sub(r"[^0-9.]", "", s)
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def fmt_money(val: float) -> str:
    # красиво: $48 или $48.50
    if abs(val - int(val)) < 1e-9:
        return f"₸{int(val)}"
    return f"₸{val:.2f}"


def money(value) -> str:
    """Jinja-хелпер: принимает cents (int) или $-строку/float и возвращает '$12.34'."""
    if value is None:
        return "—"
    # если пришла строка "$48" — парсим как доллары
    if isinstance(value, str):
        return fmt_money(parse_price_to_float(value))

    # float считаем долларами
    if isinstance(value, float):
        return fmt_money(value)

    # int считаем центами
    try:
        cents = int(value)
    except Exception:
        return "—"
    return fmt_money(cents / 100.0)


def _to_cents_from_price_str(price_str: str) -> int:
    return int(round(parse_price_to_float(price_str) * 100))


def build_cart_view():
    """
    Собирает корзину из session["cart"] (без JS).
    session["cart"] хранит {"2": 3, "5": 1}
    """
    cart = session.get("cart", {})  # {"2": 3, "5": 1}
    items = []
    total_cents = 0
    count = 0

    for k, qty in cart.items():
        try:
            item_id = int(k)
            qty = int(qty)
        except ValueError:
            continue
        if qty <= 0:
            continue

        item = get_item_by_id(item_id)
        if not item:
            continue

        # Prefer cents from DB (Supabase). Fallback to parsing "$12".
        unit_cents = int(item.get("price_cents") or 0)
        if unit_cents <= 0:
            unit_cents = _to_cents_from_price_str(item.get("price", "0"))

        line_cents = unit_cents * qty

        items.append({
            "id": item_id,
            "title": item.get("title", ""),
            "img": item.get("img", ""),
            "price_str": money(unit_cents),
            "unit_price_cents": unit_cents,
            "qty": qty,
            "line_total_cents": line_cents,
            "line_str": money(line_cents),
        })

        total_cents += line_cents
        count += qty

    return items, money(total_cents), count, total_cents


@app.context_processor
def inject_cart_into_all_templates():
    """
    Теперь cart_count / cart_items / cart_total доступны в ЛЮБОМ шаблоне,
    включая booking.html и base.html (фиксит ошибку 'cart_count is undefined').
    """
    cart_items, cart_total, cart_count, cart_total_cents = build_cart_view()
    return dict(
        cart_items=cart_items,
        cart_total=cart_total,
        cart_total_cents=cart_total_cents,
        cart_count=cart_count,
        money=money,
    )


@app.route("/")
def index():
    features = [
        {
            "icon": "🏅",
            "title": "Награды и признание",
            "text": "Рекомендован гидом Мишлен, множественные кулинарные награды"
        },
        {
            "icon": "❤",
            "title": "С любовью и страстью",
            "text": "Каждое блюдо приготовлено с тщательной заботой и художественным вниманием"
        },
        {
            "icon": "👥",
            "title": "Интимная атмосфера",
            "text": "Идеальная обстановка для романтических ужинов и торжеств"
        }
    ]

    reviews = [
        {
            "stars": 5,
            "quote": "Абсолютно божественный ужин. Boeuf Bourguignon был изысканным, а обслуживание безупречным.",
            "name": "София Лоран",
            "date": "Ноябрь 2025"
        },
        {
            "stars": 5,
            "quote": "Внимание к деталям в каждом блюде поразительно. Настоящий праздник французской кухни.",
            "name": "Марк Дюба",
            "date": "Октябрь 2025"
        },
        {
            "stars": 5,
            "quote": "Идеально для особого случая. Атмосфера и кухня создали незабываемый вечер.",
            "name": "Эмма Ричардсон",
            "date": "Октябрь 2025"
        }
    ]

    about = {
        "title": "Наша история",
        "p1": "Названный в честь легендарного художника-импрессиониста, ресторан Claude Monet воплощает пересечение художественного видения и кулинарного мастерства. С момента нашего открытия мы посвятили себя созданию незабываемых гастрономических впечатлений, которые прославляют богатые традиции французской кухни.",
        "p2": "Наш шеф-повар объединяет классические техники, передаваемые из поколения в поколение, с современными инновациями, создавая блюда, которые одновременно уходят корнями в традиции и смотрят в будущее. Каждый ингредиент тщательно отбирается у лучших поставщиков.",
        "p3": "Атмосфера Claude Monet вызывает элегантность и изысканность парижского салона, где каждая деталь — от золотых акцентов до тщательно подобранной винной карты — была разработана, чтобы перенести вас в самое сердце Франции."
    }

    return render_template(
        "index.html",
        active="home",
        features=features,
        reviews=reviews,
        about=about
    )


@app.route("/menu")
def menu():
    section = (request.args.get("section") or "zakuski").strip()
    categories, _ = get_menu_data()
    slugs = {c["slug"] for c in categories}
    if section not in slugs:
        section = "zakuski"

    grouped = group_menu_items()

    return render_template(
        "menu.html",
        active="menu",
        categories=categories,
        active_section=section,
        grouped=grouped
    )


@app.route("/dish/<int:item_id>", methods=["GET", "POST"])
def dish(item_id: int):
    item = get_item_by_id(item_id)
    if not item:
        abort(404)

    # если у блюда пока нет этих полей — не ломаемся
    item.setdefault("ingredients", [])
    item.setdefault("allergens", [])
    item.setdefault("wine_title", "Винное сопровождение")
    item.setdefault(
        "wine_text",
        "Наш сомелье рекомендует сочетать это блюдо с избранными винами из нашей тщательно подобранной винной карты. "
        "Спросите вашего официанта о персональных рекомендациях для улучшения вашего гастрономического опыта."
    )

    # qty берём из query (без JS + и - просто меняют параметр)
    try:
        qty = int(request.args.get("qty", 1))
    except ValueError:
        qty = 1
    qty = max(1, min(qty, 99))

    # Название категории на бейджике (как в макете: "Закуска")
    badge_map = {
        "zakuski": "Закуска",
        "mains": "Основное блюдо",
        "desserts": "Десерт",
        "drinks": "Напиток",
    }
    category_badge = badge_map.get(item.get("cat"), "Блюдо")

    if request.method == "POST":
        action = (request.form.get("action") or "").strip()

        # добавление в корзину
        if action == "add_to_cart":
            try:
                form_qty = int(request.form.get("qty", qty))
            except ValueError:
                form_qty = qty
            form_qty = max(1, min(form_qty, 99))

            cart = session.get("cart", {})  # { "12": 3, ... }
            key = str(item_id)
            cart[key] = int(cart.get(key, 0)) + form_qty
            session["cart"] = cart
            session.modified = True

            flash("Добавлено в корзину ✅", "success")
            return redirect(url_for("dish", item_id=item_id, qty=qty))

    return render_template(
        "dish.html",
        active="menu",
        item=item,
        qty=qty,
        category_badge=category_badge
    )


@app.route("/booking", methods=["GET", "POST"])
def booking():
    """
    Страница бронирования + корзина сверху в этом же окне (без JS):
    - cart_inc / cart_dec / cart_remove / cart_clear
    - booking_submit (или reservation_submit) отправка формы
    """
    if request.method == "POST":
        action = (request.form.get("action") or "").strip()

        # ===== корзина (кнопки) =====
        if action in {"cart_inc", "cart_dec", "cart_remove", "cart_clear"}:
            cart = session.get("cart", {})

            if action == "cart_clear":
                session["cart"] = {}
                session.modified = True
                return redirect(url_for("booking") + "#cart")

            item_id = (request.form.get("item_id") or "").strip()
            if item_id:
                key = str(item_id)
                try:
                    current = int(cart.get(key, 0))
                except ValueError:
                    current = 0

                if action == "cart_inc":
                    cart[key] = current + 1

                elif action == "cart_dec":
                    new_val = current - 1
                    if new_val <= 0:
                        cart.pop(key, None)
                    else:
                        cart[key] = new_val

                elif action == "cart_remove":
                    cart.pop(key, None)

                session["cart"] = cart
                session.modified = True

            return redirect(url_for("booking") + "#cart")

        # ===== отправка бронирования =====
        if action in {"booking_submit", "reservation_submit", ""}:
            # поддержка обоих вариантов имён полей (на всякий случай)
            full_name = (request.form.get("full_name") or request.form.get("name") or "").strip()
            email = (request.form.get("email") or "").strip()
            phone = (request.form.get("phone") or "").strip()
            date = (request.form.get("date") or "").strip()
            time = (request.form.get("time") or "").strip()
            guests_raw = (request.form.get("guests") or "1").strip()
            notes = (request.form.get("notes") or request.form.get("comment") or "").strip()

            if not full_name or not phone or not date or not time or not guests_raw:
                flash("Заполните все обязательные поля (*)", "error")
                return redirect(url_for("booking"))

            try:
                guests_int = int(guests_raw)
                if guests_int < 1 or guests_int > 20:
                    raise ValueError()
            except ValueError:
                flash("Количество гостей должно быть от 1 до 20.", "error")
                return redirect(url_for("booking"))

            cart_items, cart_total, cart_count, cart_total_cents = build_cart_view()

            # сохраняем бронь
            if USE_SUPABASE:
                try:
                    booking_row = insert_booking({
                        "full_name": full_name,
                        "email": email or None,
                        "phone": phone,
                        "booking_date": date,
                        "booking_time": time,
                        "guests": guests_int,
                        "notes": notes,
                        "cart_total_cents": int(cart_total_cents or 0),
                    })
                    booking_id = int(booking_row.get("id"))

                    # что заказали (если есть корзина)
                    items_payload = []
                    for ci in cart_items or []:
                        items_payload.append({
                            "booking_id": booking_id,
                            "menu_item_id": int(ci.get("id") or 0),
                            "title": ci.get("title") or "",
                            "qty": int(ci.get("qty") or 0),
                            "unit_price_cents": int(ci.get("unit_price_cents") or 0),
                            "line_total_cents": int(ci.get("line_total_cents") or 0),
                            "image_path": (ci.get("img") or "").lstrip("/"),
                        })
                    insert_booking_items(items_payload)

                except Exception:
                    flash("Не удалось сохранить бронь в Supabase. Проверь .env и политики RLS.", "error")
                    return redirect(url_for("booking"))
            else:
                cart_json = json.dumps(cart_items, ensure_ascii=False)
                with sqlite3.connect(DB_PATH) as con:
                    con.execute(
                        """
                        INSERT INTO bookings (name, email, phone, date, time, guests, comment, notes, cart_items, cart_total)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (full_name, email, phone, date, time, guests_int, notes, notes, cart_json, cart_total)
                    )
                    con.commit()

            # по желанию: очищаем корзину после отправки
            session["cart"] = {}
            session.modified = True

            flash("Заявка отправлена! Мы свяжемся с вами для подтверждения ✅", "success")
            return redirect(url_for("booking"))

    # GET (или если просто надо отрисовать)
    return render_template("booking.html", active="booking")


# ============================
#         ADMIN
# ============================

def _db_connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _map_booking_row(row: sqlite3.Row) -> dict:
    d = dict(row)
    total_str = (d.get("cart_total") or "").strip()
    total_cents = _to_cents_from_price_str(total_str)

    return {
        "id": d.get("id"),
        "full_name": (d.get("name") or "").strip(),
        "email": (d.get("email") or "").strip(),
        "phone": (d.get("phone") or "").strip(),
        "date": (d.get("date") or "").strip(),
        "time": (d.get("time") or "").strip(),
        "guests": d.get("guests"),
        "notes": (d.get("notes") or d.get("comment") or "").strip(),
        "created_at": d.get("created_at"),
        "cart_items": d.get("cart_items"),
        "cart_total": total_str,
        "total_cents": total_cents,
    }


def _map_booking_supabase(d: dict) -> dict:
    total_cents = int(d.get("cart_total_cents") or 0)
    return {
        "id": d.get("id"),
        "full_name": (d.get("full_name") or "").strip(),
        "email": (d.get("email") or "").strip(),
        "phone": (d.get("phone") or "").strip(),
        "date": str(d.get("booking_date") or "").strip(),
        "time": str(d.get("booking_time") or "").strip(),
        "guests": d.get("guests"),
        "notes": (d.get("notes") or "").strip(),
        "created_at": d.get("created_at"),
        "cart_total": money(total_cents),
        "total_cents": total_cents,
    }


@app.route("/admin/bookings")
def admin_bookings():
    if USE_SUPABASE:
        try:
            bookings_raw = list_bookings()
            bookings = [_map_booking_supabase(b) for b in (bookings_raw or [])]
        except Exception:
            bookings = []
            flash("Supabase недоступен: проверь .env и политики RLS", "error")
        return render_template("admin_bookings.html", active="admin", bookings=bookings)

    # fallback SQLite
    init_db()
    with _db_connect() as con:
        cur = con.execute(
            "SELECT id, name, email, phone, date, time, guests, comment, notes, cart_items, cart_total, created_at "
            "FROM bookings ORDER BY id DESC"
        )
        bookings = [_map_booking_row(r) for r in cur.fetchall()]
    return render_template("admin_bookings.html", active="admin", bookings=bookings)


@app.route("/admin/bookings/<int:reservation_id>")
def admin_booking_detail(reservation_id: int):
    if USE_SUPABASE:
        reservation_raw = get_booking(reservation_id)
        if not reservation_raw:
            abort(404)
        reservation = _map_booking_supabase(reservation_raw)
        try:
            items_raw = list_booking_items(reservation_id)
        except Exception:
            items_raw = []

        items = []
        for it in items_raw or []:
            items.append({
                "title": (it.get("title") or "").strip(),
                "image_path": (it.get("image_path") or "img/placeholder.jpg").lstrip("/"),
                "qty": int(it.get("qty") or 0),
                "unit_price_cents": int(it.get("unit_price_cents") or 0),
                "line_total_cents": int(it.get("line_total_cents") or 0),
            })

        return render_template(
            "admin_booking_detail.html",
            active="admin",
            reservation=reservation,
            items=items,
        )

    # fallback SQLite
    init_db()
    with _db_connect() as con:
        cur = con.execute(
            "SELECT id, name, email, phone, date, time, guests, comment, notes, cart_items, cart_total, created_at "
            "FROM bookings WHERE id = ?",
            (reservation_id,)
        )
        row = cur.fetchone()
        if not row:
            abort(404)

    reservation = _map_booking_row(row)

    # разбираем заказ (cart_items хранится как JSON)
    raw_items = []
    try:
        if reservation.get("cart_items"):
            raw_items = json.loads(reservation["cart_items"])
    except Exception:
        raw_items = []

    items = []
    for it in raw_items or []:
        title = (it.get("title") or "").strip()
        img = (it.get("img") or it.get("image_path") or "img/placeholder.jpg").lstrip("/")
        qty = int(it.get("qty") or 0)
        if qty <= 0:
            continue

        # unit price
        if "unit_price_cents" in it:
            unit_cents = int(it.get("unit_price_cents") or 0)
        elif "unit" in it:
            unit_cents = int(round(float(it.get("unit") or 0) * 100))
        else:
            unit_cents = _to_cents_from_price_str(it.get("price_str") or it.get("price") or "")

        line_cents = unit_cents * qty

        items.append({
            "title": title,
            "image_path": img,
            "qty": qty,
            "unit_price_cents": unit_cents,
            "line_total_cents": line_cents,
        })

    return render_template(
        "admin_booking_detail.html",
        active="admin",
        reservation=reservation,
        items=items,
    )


@app.route("/admin/menu/new", methods=["GET", "POST"])
def admin_menu_new():
    """Админка: добавление категорий и блюд.

    Если настроен Supabase — пишет в Postgres.
    Если нет — fallback в menu_data.json.
    """

    tab = (request.args.get("tab") or "item").strip()
    if tab not in {"item", "category"}:
        tab = "item"

    categories, items = (get_menu_data() if USE_SUPABASE else load_menu_data())

    if request.method == "POST":
        form_type = (request.form.get("form_type") or "").strip()

        # ---- добавить категорию ----
        if form_type == "category":
            label = (request.form.get("label") or "").strip()
            slug = _slugify(request.form.get("slug") or "")
            if not label:
                flash("Введите название категории", "error")
                return redirect(url_for("admin_menu_new", tab="category"))

            if slug == "category":
                slug = _slugify(label)

            existing = {c.get("slug") for c in (categories or [])}
            base = slug
            i = 2
            while slug in existing:
                slug = f"{base}-{i}"
                i += 1

            if USE_SUPABASE:
                try:
                    upsert_category(slug, label)
                except Exception:
                    flash("Не удалось добавить категорию в Supabase", "error")
                    return redirect(url_for("admin_menu_new", tab="category"))
                # обновим кеш
                get_menu_data(force=True)
            else:
                categories.append({"slug": slug, "label": label})
                save_menu_data(categories, items)

            flash("Категория добавлена ✅", "success")
            return redirect(url_for("admin_menu_new", tab="category"))

        # ---- добавить блюдо ----
        if form_type == "item":
            category_slug = (request.form.get("category_slug") or "").strip()
            title = (request.form.get("title") or "").strip()
            description = (request.form.get("description") or "").strip()
            price = (request.form.get("price") or "").strip()

            if not category_slug or not title or not description or not price:
                flash("Заполните обязательные поля (*)", "error")
                return redirect(url_for("admin_menu_new", tab="item"))

            price_cents = int(round(parse_price_to_float(price) * 100))

            # картинка: либо путь, либо загрузка
            image_path = (request.form.get("image_path") or "").strip().lstrip("/")
            file = request.files.get("image_file")
            if file and file.filename:
                filename = secure_filename(file.filename)
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{stamp}_{filename}"
                dest = UPLOAD_DIR / filename
                file.save(dest)
                image_path = f"uploads/{filename}"

            if not image_path:
                image_path = "img/placeholder.jpg"

            ingredients = (request.form.get("ingredients") or "").strip()
            allergens = (request.form.get("allergens") or "").strip()
            wine_title = (request.form.get("wine_title") or "").strip()
            wine_text = (request.form.get("wine_text") or "").strip()

            if USE_SUPABASE:
                payload = {
                    "category_slug": category_slug,
                    "title": title,
                    "description": description,
                    "ingredients": ingredients,
                    "allergens": allergens,
                    "price_cents": price_cents,
                    "image_path": image_path,
                    "wine_title": wine_title or None,
                    "wine_text": wine_text or None,
                }
                try:
                    insert_menu_item(payload)
                except Exception:
                    flash("Не удалось добавить блюдо в Supabase", "error")
                    return redirect(url_for("admin_menu_new", tab="item"))
                get_menu_data(force=True)
            else:
                new_id = (max([x.get("id", 0) for x in items]) + 1) if items else 1
                new_item = {
                    "id": new_id,
                    "cat": category_slug,
                    "title": title,
                    "price": money(price_cents),
                    "price_cents": price_cents,
                    "desc": description,
                    "img": image_path,
                }
                if ingredients:
                    new_item["ingredients"] = [s.strip() for s in ingredients.split(",") if s.strip()]
                if allergens:
                    new_item["allergens"] = [s.strip() for s in allergens.split(",") if s.strip()]
                if wine_title:
                    new_item["wine_title"] = wine_title
                if wine_text:
                    new_item["wine_text"] = wine_text

                items.append(new_item)
                save_menu_data(categories, items)

            flash("Блюдо добавлено ✅", "success")
            return redirect(url_for("admin_menu_new", tab="item"))

    # для рендера всегда берём актуальные категории
    categories, _ = (get_menu_data() if USE_SUPABASE else load_menu_data())
    return render_template(
        "admin_menu_new.html",
        active="admin",
        tab=tab,
        categories=categories,
    )


if __name__ == "__main__":
    if USE_SUPABASE:
        ensure_supabase_seed()
    else:
        init_db()
    app.run(debug=True)
