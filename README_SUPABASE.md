# Supabase подключение (Claude Monet)

## 1) Создай таблицы в Supabase
1. Supabase Dashboard → **SQL Editor**
2. Вставь и выполни файл: `supabase_schema.sql`

> Важно: политики в SQL сейчас **разрешают anon читать/писать** (демо).  
> Если это реальный проект — сделаем нормальную авторизацию/роли и закроем доступ.

## 2) Добавь переменные окружения
- Скопируй `.env.example` → `.env`
- Вставь свой ключ в `SUPABASE_ANON_KEY`

## 3) Установи зависимости
```bash
pip install -r requirements.txt
```

## 4) Запусти проект
```bash
python app.py
```

## Ссылки
- Сайт: `/` , `/menu`, `/booking`
- Админка:
  - `/admin/bookings`
  - `/admin/menu/new`
