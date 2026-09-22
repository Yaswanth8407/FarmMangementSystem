"""FarmOS AI engine.

Uses Google Gemini when GEMINI_API_KEY is set; otherwise falls back to a
deterministic on-device analysis engine so the app stays useful without a key.
"""

import os
import re
import time
from datetime import date, datetime, timedelta
import db
import weather as weatherModule

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
_weather_cache = {"time": 0, "data": None}
_forecast_cache = {"time": 0, "data": None}

SYSTEM_PROMPT = (
    "You are FarmOS AI, a precision agricultural assistant for a small farm. "
    "You are given the farm's current data (crops, inventory, sales, expenses "
    "and weather). Answer the farmer's question using that data directly. "
    "Be concise, practical and professional. Use plain text with bullets and "
    "relevant emojis. Always cite the actual numbers/items from the farm data "
    "you were given - never invent figures."
)


def _get_api_key():
    return os.getenv("GEMINI_API_KEY", "").strip()


def is_ai_configured():
    return bool(_get_api_key())


def _cached_weather():
    now = time.time()
    if now - _weather_cache["time"] > 900:
        try:
            _weather_cache["data"] = weatherModule.get_weather("Mumbai")
        except Exception:
            _weather_cache["data"] = None
        _weather_cache["time"] = now
    return _weather_cache["data"]


def _cached_forecast():
    now = time.time()
    if now - _forecast_cache["time"] > 900:
        try:
            _forecast_cache["data"] = weatherModule.get_forecast("Mumbai", 5)
        except Exception:
            _forecast_cache["data"] = []
        _forecast_cache["time"] = now
    return _forecast_cache["data"] or []


def _weekday_name(iso_date):
    parsed = _to_iso_date(iso_date)
    return parsed.strftime("%A") if parsed else (iso_date or "")


def build_forecast_alerts(max_alerts=4):
    """Combine the 5-day forecast with crop stage and calendar tasks."""
    forecast = _cached_forecast()
    if not forecast:
        return []

    rainy_days = {f["date"]: f for f in forecast if f.get("will_rain")}
    crops = db.get_crops()
    alerts = []

    for task in db.get_crop_tasks():
        if task["done"] or not task["due_date"] or task["due_date"] not in rainy_days:
            continue
        day = rainy_days[task["due_date"]]
        weekday = _weekday_name(task["due_date"])
        task_type = (task["task_type"] or "").lower()
        crop = task["crop_name"] or "the crop"
        if task["task_type"] in ("Fertilizer", "Pest check"):
            alerts.append(
                f"Rain on {weekday}, postpone the {task_type} task for {crop}."
            )
        elif task["task_type"] == "Irrigation":
            alerts.append(f"Rain on {weekday}, skip irrigation for {crop}.")
        elif task["task_type"] == "Harvest":
            alerts.append(f"Rain on {weekday}, protect the {crop} harvest.")
        else:
            alerts.append(f"Rain on {weekday}, review the '{task['title']}' task for {crop}.")
        if len(alerts) >= max_alerts:
            return alerts

    # Crop-stage heat watch.
    for day in forecast[:3]:
        temp_max = day.get("temp_max")
        if temp_max is not None and temp_max >= 38:
            growing = [c["name"] for c in crops if (c["status"] or "") != "Harvested"]
            if growing:
                alerts.append(
                    f"Heat on {_weekday_name(day['date'])} (max {temp_max:.0f}C) - "
                    f"water {growing[0]} early morning."
                )
            break

    return alerts[:max_alerts]


def get_farm_context():
    """Rich text snapshot of farm data, used in AI prompts."""
    crops = db.get_crops()
    inventory = db.get_inventory()
    sales = db.get_sales()
    expenses = db.get_expenses()
    weather = _cached_weather()

    total_sales = sum(s["quantity"] * s["price"] for s in sales)
    total_exp = sum(e["amount"] for e in expenses)

    lines = ["CURRENT FARM DATA"]
    lines.append("- Farm located near: Mumbai")

    lines.append(f"- Crops ({len(crops)}):")
    for c in crops:
        harvest = c["expected_harvest_date"] or "?"
        days = db.days_until(c["expected_harvest_date"])
        if days is None:
            harvest_note = ""
        elif days < 0:
            harvest_note = f" (overdue by {abs(days)} days)"
        else:
            harvest_note = f" ({days} days left)"
        lines.append(
            f"    - {c['name']} | area {c['area'] or '?'} | "
            f"planted {c['planting_date'] or '?'} | status {c['status'] or '?'} | "
            f"expected harvest {harvest}{harvest_note}"
        )

    lines.append(f"- Inventory ({len(inventory)} items):")
    for it in inventory:
        threshold = it["reorder_threshold"] or 0
        lines.append(
            f"    - {it['item_name']} | qty {it['quantity']:g} {it['unit'] or ''} "
            f"| reorder at {threshold:g} "
            f"| {'LOW STOCK' if db.is_low_stock(it) else 'in stock'}"
        )

    lines.append(f"- Sales ({len(sales)}):")
    for s in sales:
        lines.append(
            f"    - {s['crop_name']} | {s['quantity']:g} units @ Rs.{s['price']:g} "
            f"= Rs.{s['quantity'] * s['price']:,.2f} | {s['sale_date']}"
        )

    lines.append(f"- Expenses ({len(expenses)}):")
    for e in expenses:
        lines.append(
            f"    - {e['category']} | Rs.{e['amount']:,.2f} | {e['expense_date']} "
            f"| {e['description'] or ''}"
        )

    lines.append(f"- Total revenue: Rs.{total_sales:,.2f}")
    lines.append(f"- Total expenses: Rs.{total_exp:,.2f}")
    lines.append(f"- Net profit: Rs.{total_sales - total_exp:,.2f}")

    profit_by_crop = db.get_profit_by_crop()
    if profit_by_crop:
        lines.append("- Profit by crop:")
        for entry in profit_by_crop:
            lines.append(
                f"    - {entry['name']} | revenue Rs.{entry['sales']:,.2f} | "
                f"cost Rs.{entry['expenses']:,.2f} | profit Rs.{entry['profit']:,.2f}"
            )

    if weather:
        lines.append(
            f"- Weather (Mumbai): {weather['temperature']}C, "
            f"{weather['condition']}, humidity {weather['humidity']}%, "
            f"wind {weather['wind']} km/h"
        )
    else:
        lines.append("- Weather: unavailable")

    forecast = _cached_forecast()
    if forecast:
        lines.append("- 5-day forecast:")
        for day in forecast:
            temp_range = ""
            if day.get("temp_min") is not None and day.get("temp_max") is not None:
                temp_range = f" | {day['temp_min']:.0f}-{day['temp_max']:.0f}C"
            rain = ""
            if day.get("will_rain"):
                rain = f" | rain {day.get('rain', 0):.1f}mm ({day.get('pop', 0):.0f}% chance)"
            lines.append(
                f"    - {_weekday_name(day['date'])} | {day.get('condition', '?')}"
                f"{temp_range}{rain}"
            )

    alerts = build_forecast_alerts()
    if alerts:
        lines.append("- Weather-aware alerts:")
        for alert in alerts:
            lines.append(f"    - {alert}")

    return "\n".join(lines)


def _fallback_answer(message):
    """On-device answer engine with real farm-data analysis."""
    m = message.lower()
    sales = db.get_sales()
    expenses = db.get_expenses()
    crops = db.get_crops()
    inventory = db.get_inventory()
    total_sales = db.get_total_sales()
    total_exp = db.get_total_expenses()
    profit = total_sales - total_exp
    weather = _cached_weather()

    if any(k in m for k in ("profit", "loss", "revenue", "financial", "earn", "money", "income")):
        lines = ["Financial snapshot"]
        lines.append(f"  - Revenue: Rs.{total_sales:,.0f}")
        lines.append(f"  - Expenses: Rs.{total_exp:,.0f}")
        lines.append(f"  - Net profit: Rs.{profit:,.0f}")
        lines.append("Your farm is " + ("healthy" if profit > 0 else "in the red") + ".")
        cats = {}
        for e in expenses:
            cats[e["category"]] = cats.get(e["category"], 0) + e["amount"]
        if cats:
            biggest = max(cats, key=cats.get)
            lines.append(f"Biggest cost center: {biggest} (Rs.{cats[biggest]:,.0f}).")
        return "\n".join(lines)

    if any(k in m for k in ("crop", "plant", "grow", "harvest", "field")):
        if not crops:
            return "You have no crops recorded yet. Add crops from the Crops page first."
        lines = ["Your crops"]
        for c in crops[:8]:
            days = db.days_until(c["expected_harvest_date"])
            if days is None:
                harvest = "harvest date not set"
            elif days < 0:
                harvest = f"harvest overdue by {abs(days)} day(s)"
            else:
                harvest = f"{days} day(s) to harvest"
            lines.append(
                f"  - {c['name']} - {c['area'] or '?'}, {c['status'] or 'no status'} "
                f"({harvest})"
            )
        if weather:
            temp = weather["temperature"]
            advice = ("Water crops early morning - it's hot" if temp > 35
                      else "Temperature is fine for regular fieldwork")
            lines.append(f"Weather advice: {advice}.")
        return "\n".join(lines)

    if any(k in m for k in ("stock", "inventory", "suppl", "fertil", "seed", "store", "material")):
        if not inventory:
            return "No inventory items recorded yet. Add them from the Inventory page."
        lines = ["Inventory"]
        low = [it for it in inventory if db.is_low_stock(it)]
        for it in inventory[:8]:
            flag = " [LOW]" if db.is_low_stock(it) else ""
            lines.append(f"  - {it['item_name']}: {it['quantity']:g} {it['unit'] or ''}{flag}")
        if low:
            lines.append("Low-stock items - restock soon: " + ", ".join(i["item_name"] for i in low))
        return "\n".join(lines)

    if any(k in m for k in ("expense", "spend", "cost", "budget")):
        if not expenses:
            return "No expenses recorded yet."
        cats = {}
        for e in expenses:
            cats[e["category"]] = cats.get(e["category"], 0) + e["amount"]
        lines = ["Expenses by category"]
        for cat, amt in sorted(cats.items(), key=lambda x: x[1], reverse=True):
            pct = (amt / total_exp * 100) if total_exp else 0
            lines.append(f"  - {cat}: Rs.{amt:,.0f} ({pct:.0f}%)")
        return "\n".join(lines)

    if any(k in m for k in ("weather", "rain", "temperature", "water", "irrigat", "humidity", "wind")):
        if not weather:
            return "Weather data is unavailable right now. Check your connection."
        return "\n".join(weatherModule.get_farming_suggestion(weather))

    if any(k in m for k in ("analyze", "analysis", "insight", "summary", "report", "overview", "recommend", "advice", "suggest", "help", "how is")):
        return analyze_farm()

    if any(k in m for k in ("hi", "hello", "hey", "namaste")):
        return ("Hello! I'm FarmOS AI. I can analyze your farm data, check your "
                "finances, crops, inventory or advise on weather. Try asking "
                "'Analyze my farm' or 'How is my profit?'")

    return ("I can help you with:\n"
            "  - Analyze my farm\n"
            "  - How is my profit?\n"
            "  - Which crops do I have?\n"
            "  - Inventory / low stock status\n"
            "  - Weather-based farming advice\n\n"
            "Set the GEMINI_API_KEY environment variable to unlock full AI chat.")


def build_insights():
    """Deterministic daily insights used on the dashboard and chat."""
    sales = db.get_sales()
    expenses = db.get_expenses()
    crops = db.get_crops()
    inventory = db.get_inventory()
    total_sales = db.get_total_sales()
    total_exp = db.get_total_expenses()
    profit = total_sales - total_exp
    weather = _cached_weather()

    insights = []

    if weather:
        insights.extend(weatherModule.get_farming_suggestion(weather)[:2])
    else:
        insights.append("Weather data unavailable - check your connection.")

    insights.extend(build_forecast_alerts(2))

    low_stock = db.get_low_stock_items()
    if low_stock:
        names = ", ".join(i["item_name"] for i in low_stock[:3])
        insights.append(f"Restock soon: {names} dropped to their reorder threshold.")

    if crops:
        growing = [c for c in crops if (c["status"] or "") != "Harvested"]
        if growing:
            insights.append(
                f"{len(growing)} crop(s) need care right now - check "
                f"{growing[0]['name']} first."
            )

        upcoming = [
            (c["name"], db.days_until(c["expected_harvest_date"]))
            for c in crops
            if (c["status"] or "") != "Harvested"
            and db.days_until(c["expected_harvest_date"]) is not None
            and db.days_until(c["expected_harvest_date"]) <= 7
        ]
        if upcoming:
            upcoming.sort(key=lambda x: x[1])
            name, days = upcoming[0]
            when = "today" if days == 0 else (
                f"overdue by {abs(days)} day(s)" if days < 0 else f"in {days} day(s)"
            )
            insights.append(f"Harvest watch: {name} is due {when}.")

    if sales:
        top = max(sales, key=lambda s: s["quantity"] * s["price"])
        insights.append(
            f"Best seller: {top['crop_name']} earned "
            f"Rs.{top['quantity'] * top['price']:,.0f}."
        )

    crop_profits = db.get_profit_by_crop()
    if crop_profits:
        best = max(crop_profits, key=lambda p: p["profit"])
        worst = min(crop_profits, key=lambda p: p["profit"])
        insights.append(
            f"Most profitable crop: {best['name']} (Rs.{best['profit']:,.0f})."
        )
        if worst["profit"] < 0:
            insights.append(
                f"Losing money on {worst['name']} (Rs.{worst['profit']:,.0f})."
            )

    cats = {}
    for e in expenses:
        cats[e["category"]] = cats.get(e["category"], 0) + e["amount"]
    if cats:
        biggest = max(cats, key=cats.get)
        insights.append(f"Watch spending on {biggest} (Rs.{cats[biggest]:,.0f} total).")

    insights.append(
        f"Net result: Rs.{profit:,.0f} - your farm is "
        + ("profitable." if profit > 0 else "overspent.")
    )

    return insights[:6]


def analyze_farm():
    total_sales = db.get_total_sales()
    total_exp = db.get_total_expenses()
    lines = ["Farm Analysis"]
    lines.append(f"  - Revenue: Rs.{total_sales:,.0f}")
    lines.append(f"  - Expenses: Rs.{total_exp:,.0f}")
    lines.append(f"  - Net profit: Rs.{total_sales - total_exp:,.0f}")
    lines.append("")
    lines.append("Actions:")
    for tip in build_insights():
        lines.append("  " + tip)
    return "\n".join(lines)


_chat_history = []


# ---------------------------------------------------------------------------
# Tool-calling agent: read tools run immediately, write tools need confirmation
# ---------------------------------------------------------------------------

READ_TOOLS = ("get_sales", "get_crops", "get_profit_by_crop")
WRITE_TOOLS = ("add_sale", "add_expense", "add_crop")
MAX_HISTORY_TURNS = 12

_LANGUAGES = {
    "en": ("English", "en-IN"),
    "hi": ("Hindi", "hi-IN"),
    "mr": ("Marathi", "mr-IN"),
    "te": ("Telugu", "te-IN"),
}


def language_name(code):
    return _LANGUAGES.get((code or "en").lower(), _LANGUAGES["en"])[0]


def speech_locale(code):
    return _LANGUAGES.get((code or "en").lower(), _LANGUAGES["en"])[1]


def _agent_system_prompt(language=None):
    prompt = (
        "You are FarmOS AI, a precision agriculture assistant for a small farm "
        "near Mumbai, India. Reply in the SAME LANGUAGE the farmer used "
        "(English, Hindi, Marathi or Telugu). Be concise, practical and friendly "
        "with short bullets.\n\n"
        "You can call tools to read and write farm data.\n"
        "- Read tools (get_sales, get_crops, get_profit_by_crop) run immediately.\n"
        "- Write tools (add_sale, add_expense, add_crop) are NOT executed until "
        "the farmer confirms. Call the write tool with the details you understood; "
        "the app shows a confirmation card. Never say a write already happened - "
        "say you have prepared it and ask for confirmation.\n\n"
        "When the farmer describes something in natural language (for example "
        "'sold 40 kg onions at 22 yesterday'), call add_sale with the parsed "
        "values. For expenses use one of these categories: "
        + ", ".join(db.EXPENSE_CATEGORIES) + ".\n"
        "Today's date is " + date.today().isoformat() + ". Resolve relative dates "
        "like 'yesterday' or 'last week' yourself before calling a tool."
    )
    if language:
        prompt += f"\n\nPrefer replying in {language_name(language)}."
    return prompt


def _build_tool(genai):
    p = genai.protos

    def schema(kind, description):
        return p.Schema(type=kind, description=description)

    string = p.Type.STRING
    number = p.Type.NUMBER
    integer = p.Type.INTEGER

    declarations = [
        p.FunctionDeclaration(
            name="get_sales",
            description="List recorded sales, newest first. Optionally filter by crop name.",
            parameters=p.Schema(
                type=p.Type.OBJECT,
                properties={
                    "crop_name": schema(string, "Only return sales for this crop (optional)."),
                    "limit": schema(integer, "Maximum number of sales to return (default 10)."),
                },
            ),
        ),
        p.FunctionDeclaration(
            name="get_crops",
            description="List every crop with area, planting date, status and expected harvest date.",
        ),
        p.FunctionDeclaration(
            name="get_profit_by_crop",
            description="Get revenue, expenses and profit for each crop.",
        ),
        p.FunctionDeclaration(
            name="add_sale",
            description="Prepare to record a sale of a crop. Needs farmer confirmation before saving.",
            parameters=p.Schema(
                type=p.Type.OBJECT,
                properties={
                    "crop_name": schema(string, "Name of the crop sold."),
                    "quantity": schema(number, "Quantity sold."),
                    "price": schema(number, "Price per unit."),
                    "sale_date": schema(string, "Sale date as YYYY-MM-DD (defaults to today)."),
                },
                required=["crop_name", "quantity", "price"],
            ),
        ),
        p.FunctionDeclaration(
            name="add_expense",
            description="Prepare to record an expense. Needs farmer confirmation before saving.",
            parameters=p.Schema(
                type=p.Type.OBJECT,
                properties={
                    "category": schema(string, "One of: " + ", ".join(db.EXPENSE_CATEGORIES)),
                    "amount": schema(number, "Amount spent."),
                    "expense_date": schema(string, "Expense date as YYYY-MM-DD (defaults to today)."),
                    "description": schema(string, "Short description (optional)."),
                    "crop_name": schema(string, "Crop this expense relates to (optional)."),
                },
                required=["category", "amount"],
            ),
        ),
        p.FunctionDeclaration(
            name="add_crop",
            description="Prepare to add a new crop. Needs farmer confirmation before saving.",
            parameters=p.Schema(
                type=p.Type.OBJECT,
                properties={
                    "name": schema(string, "Crop name."),
                    "area": schema(string, "Area such as '2 acres' (optional)."),
                    "planting_date": schema(string, "Planting date as YYYY-MM-DD (optional)."),
                    "status": schema(string, "One of: " + ", ".join(db.CROP_STATUSES)),
                },
                required=["name"],
            ),
        ),
    ]
    return p.Tool(function_declarations=declarations)


def _fmt_num(value):
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return "?"


def _resolve_crop_id(crop_name):
    name = (crop_name or "").strip().lower()
    if not name:
        return None
    crops = db.get_crops()
    for crop in crops:
        if (crop["name"] or "").strip().lower() == name:
            return crop["id"]
    for crop in crops:
        if name in (crop["name"] or "").strip().lower():
            return crop["id"]
    return None


def _run_tool(name, args):
    """Execute a read tool and return JSON-serialisable data."""
    args = dict(args or {})
    if name == "get_sales":
        rows = db.get_sales()
        crop = (args.get("crop_name") or "").strip().lower()
        if crop:
            rows = [r for r in rows if crop in (r["crop_name"] or "").lower()]
        try:
            limit = int(args.get("limit") or 10)
        except (TypeError, ValueError):
            limit = 10
        rows = rows[:max(1, min(limit, 50))]
        return [
            {
                "crop_name": r["crop_name"],
                "quantity": r["quantity"],
                "price": r["price"],
                "sale_date": r["sale_date"],
                "total": round((r["quantity"] or 0) * (r["price"] or 0), 2),
            }
            for r in rows
        ]
    if name == "get_crops":
        return [
            {
                "name": c["name"],
                "area": c["area"],
                "planting_date": c["planting_date"],
                "status": c["status"],
                "expected_harvest_date": c["expected_harvest_date"],
                "days_to_harvest": db.days_until(c["expected_harvest_date"]),
            }
            for c in db.get_crops()
        ]
    if name == "get_profit_by_crop":
        return [
            {
                "name": p["name"],
                "sales": round(p["sales"], 2),
                "expenses": round(p["expenses"], 2),
                "profit": round(p["profit"], 2),
            }
            for p in db.get_profit_by_crop()
        ]
    return {"error": f"Unknown tool: {name}"}


def _normalise_action(name, args):
    args = dict(args or {})
    if name == "add_sale":
        args["crop_name"] = (args.get("crop_name") or "").strip()
        args["quantity"] = _to_float(args.get("quantity"))
        args["price"] = _to_float(args.get("price"))
        args["sale_date"] = _normalise_date(args.get("sale_date")) or date.today().isoformat()
    elif name == "add_expense":
        args["category"] = _closest_category(args.get("category"))
        args["amount"] = _to_float(args.get("amount"))
        args["expense_date"] = _normalise_date(args.get("expense_date")) or date.today().isoformat()
        args["description"] = (args.get("description") or "").strip()
        args["crop_name"] = (args.get("crop_name") or "").strip()
    elif name == "add_crop":
        args["name"] = (args.get("name") or "").strip()
        args["area"] = (args.get("area") or "").strip()
        args["planting_date"] = _normalise_date(args.get("planting_date")) or ""
        status = (args.get("status") or "").strip().title()
        args["status"] = status if status in db.CROP_STATUSES else "Planted"
    return args


def _describe_action(name, args):
    if name == "add_sale":
        return (
            f"Record sale: {_fmt_num(args.get('quantity'))} of "
            f"{args.get('crop_name')} at Rs.{_fmt_num(args.get('price'))} "
            f"on {args.get('sale_date')}"
        )
    if name == "add_expense":
        detail = f" - {args['description']}" if args.get("description") else ""
        return (
            f"Record expense: {args.get('category')} "
            f"Rs.{_fmt_num(args.get('amount'))} on {args.get('expense_date')}{detail}"
        )
    if name == "add_crop":
        extra = f" ({args.get('area')})" if args.get("area") else ""
        planted = f", planted {args.get('planting_date')}" if args.get("planting_date") else ""
        return f"Add crop: {args.get('name')}{extra}{planted}, status {args.get('status')}"
    return name


def _make_action(name, raw_args):
    args = _normalise_action(name, raw_args)
    return {"tool": name, "args": args, "summary": _describe_action(name, args)}


def execute_pending_action(action):
    """Run a confirmed write action. Returns a human-readable result string."""
    name = action.get("tool")
    args = action.get("args") or {}
    if name == "add_sale":
        crop_name = args.get("crop_name") or "Unknown"
        quantity = args.get("quantity")
        price = args.get("price")
        if quantity is None or price is None:
            return "Could not record the sale - quantity or price was missing."
        sale_date = args.get("sale_date") or date.today().isoformat()
        db.add_sale(crop_name, quantity, price, sale_date, _resolve_crop_id(crop_name))
        return (
            f"Done. Recorded sale: {_fmt_num(quantity)} of {crop_name} at "
            f"Rs.{_fmt_num(price)} on {sale_date}."
        )
    if name == "add_expense":
        amount = args.get("amount")
        if amount is None:
            return "Could not record the expense - amount was missing."
        category = args.get("category") or "Other"
        expense_date = args.get("expense_date") or date.today().isoformat()
        db.add_expense(
            category, amount, expense_date, args.get("description", ""),
            _resolve_crop_id(args.get("crop_name"))
        )
        return f"Done. Recorded expense: {category} Rs.{_fmt_num(amount)} on {expense_date}."
    if name == "add_crop":
        crop_name = args.get("name")
        if not crop_name:
            return "Could not add the crop - name was missing."
        crop_id = db.add_crop(
            crop_name, args.get("area", ""), args.get("planting_date", ""),
            args.get("status") or "Planted", None
        )
        if args.get("planting_date"):
            try:
                tasks = generate_crop_calendar(
                    crop_name, args["planting_date"], args.get("area")
                )
                db.add_crop_tasks(crop_id, crop_name, tasks)
            except Exception:
                pass
        return f"Done. Added crop {crop_name}."
    return "Unknown action."


def _agent_with_gemini(message, history, language=None):
    import google.generativeai as genai

    genai.configure(api_key=_get_api_key())
    tool = _build_tool(genai)
    model = genai.GenerativeModel(
        MODEL_NAME, system_instruction=_agent_system_prompt(language), tools=[tool]
    )

    contents = []
    for turn in (history or [])[-MAX_HISTORY_TURNS:]:
        role = "user" if turn["role"] == "user" else "model"
        text = (turn["text"] or "").strip()
        if text:
            contents.append({"role": role, "parts": [text]})
    contents.append({"role": "user", "parts": [message]})

    last_text = ""
    for _ in range(5):
        response = model.generate_content(contents, tools=[tool])
        candidate = response.candidates[0]
        parts = list(candidate.content.parts)
        calls = [p.function_call for p in parts if p.function_call and p.function_call.name]
        text = "".join(getattr(p, "text", "") or "" for p in parts).strip()
        if text:
            last_text = text

        if not calls:
            return {"type": "text", "text": text or "(no reply)"}

        write_calls = [c for c in calls if c.name in WRITE_TOOLS]
        if write_calls:
            actions = [_make_action(c.name, dict(c.args)) for c in write_calls]
            return {"type": "action", "text": text, "actions": actions}

        contents.append(candidate.content)
        response_parts = []
        for call in calls:
            result = _run_tool(call.name, dict(call.args))
            response_parts.append(
                genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=call.name, response={"result": result}
                    )
                )
            )
        contents.append({"role": "user", "parts": response_parts})

    return {"type": "text", "text": last_text or "Sorry, I couldn't complete that request."}


_SALE_RE = re.compile(
    r"(?:sold|sell)\s+(?P<qty>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>kg|kgs|quintals?|tonnes?|tons?|units?|bags?|pieces?|dozens?|litres?|liters?|l|ml)?"
    r"\s*(?:of\s+)?(?P<crop>[A-Za-z][A-Za-z .'-]{1,30}?)\s+"
    r"(?:at|@|for)\s+(?:rs\.?\s*|₹\s*)?(?P<price>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def _fallback_agent(message):
    """Offline agent: parse a simple sale sentence, otherwise analyse locally."""
    lowered = message.lower()
    match = _SALE_RE.search(message)
    if match and "sold" in lowered or (match and "sell" in lowered):
        crop = match.group("crop").strip(" .")
        if crop:
            sale_date = date.today().isoformat()
            if "yesterday" in lowered:
                sale_date = (date.today() - timedelta(days=1)).isoformat()
            action = _make_action("add_sale", {
                "crop_name": crop,
                "quantity": match.group("qty"),
                "price": match.group("price"),
                "sale_date": sale_date,
            })
            return {
                "type": "action",
                "text": "I've prepared this sale from your message. Please confirm:",
                "actions": [action],
            }
    return {"type": "text", "text": _fallback_answer(message)}


def agent_reply(message, history=None, language=None):
    """Return {'type': 'text'|'action', 'text': str, 'actions': [...]}.

    Gemini is asked to call tools. Reads are executed inline; writes are returned
    as pending actions so the UI can show a confirmation card first.
    """
    message = (message or "").strip()
    if not message:
        return {"type": "text", "text": "Please type a message first."}

    history = history or []
    if is_ai_configured():
        try:
            return _agent_with_gemini(message, history, language)
        except Exception as exc:
            fallback = _fallback_agent(message)
            note = f"\n\n(Note: Gemini call failed - {exc}. Showing local analysis.)"
            fallback["text"] = (fallback.get("text") or "") + note
            return fallback
    return _fallback_agent(message)


def resolve_with_gemini(message):
    """Legacy helper: single-turn Gemini answer using live farm data."""
    import google.generativeai as genai

    genai.configure(api_key=_get_api_key())
    model = genai.GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_PROMPT)
    prompt = f"{get_farm_context()}\n\nFarmer: {message}\nFarmerOS AI:"
    response = model.generate_content(prompt)
    return response.text.strip()


def get_chat_response(message, history=None, language=None):
    """Text-only reply (used as a fallback and by the CLI)."""
    result = agent_reply(message, history, language)
    if result.get("type") == "text":
        return result.get("text", "")
    lines = [result.get("text") or "I've prepared the following action - please confirm:"]
    lines += ["  - " + action["summary"] for action in result.get("actions", [])]
    return "\n".join(lines)


def clear_chat_history():
    _chat_history.clear()



# ---------------------------------------------------------------------------
# Shared helpers for the vision + calendar features
# ---------------------------------------------------------------------------

def _parse_json(text):
    """Best-effort JSON extraction from an LLM reply (handles code fences)."""
    import json

    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text[:4].lower() == "json":
            text = text[4:].strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                continue
    return None


def _to_float(value):
    if value is None:
        return None
    try:
        cleaned = str(value).replace(",", "").replace("₹", "").replace("$", "").strip()
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def _to_iso_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _normalise_date(value):
    """Return an ISO date string, or None if it cannot be understood."""
    if not value:
        return None
    text = str(value).strip()
    lowered = text.lower()
    today = date.today()
    relative = {
        "today": today, "tod": today, "now": today,
        "yesterday": today - timedelta(days=1), "yday": today - timedelta(days=1),
        "tomorrow": today + timedelta(days=1), "tmrw": today + timedelta(days=1),
        "day before yesterday": today - timedelta(days=2),
        "day after tomorrow": today + timedelta(days=2),
    }
    if lowered in relative:
        return relative[lowered].isoformat()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y",
                "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _closest_category(value):
    """Map a free-text category to one of db.EXPENSE_CATEGORIES."""
    text = (value or "").lower()
    for cat in db.EXPENSE_CATEGORIES:
        if cat.lower() in text:
            return cat
    keyword_map = {
        "seed": "Seeds", "sapling": "Seeds", "nursery": "Seeds",
        "fertil": "Fertilizer", "urea": "Fertilizer", "dap": "Fertilizer",
        "npk": "Fertilizer", "manure": "Fertilizer", "compost": "Fertilizer",
        "pestic": "Pesticide", "insect": "Pesticide", "herbic": "Pesticide",
        "fungic": "Pesticide", "spray": "Pesticide", "weed": "Pesticide",
        "diesel": "Fuel", "petrol": "Fuel", "fuel": "Fuel",
        "labour": "Labor", "labor": "Labor", "wage": "Labor",
        "repair": "Maintenance", "spare": "Maintenance",
        "pump": "Irrigation", "drip": "Irrigation", "sprinkler": "Irrigation",
        "tractor": "Equipment", "machine": "Equipment", "tool": "Equipment",
        "transport": "Transport", "freight": "Transport", "delivery": "Transport",
    }
    for key, cat in keyword_map.items():
        if key in text:
            return cat
    return "Other"


def _closest_task_type(value):
    text = (value or "").lower()
    mapping = {
        "water": "Irrigation", "irrigat": "Irrigation", "moisture": "Irrigation",
        "fertil": "Fertilizer", "nutrient": "Fertilizer", "manure": "Fertilizer",
        "pest": "Pest check", "disease": "Pest check", "scout": "Pest check",
        "harvest": "Harvest", "yield": "Harvest", "cutting": "Harvest",
    }
    for key, task_type in mapping.items():
        if key in text:
            return task_type
    return "Other"


# ---------------------------------------------------------------------------
# Feature 1: bill / receipt scanning (Gemini vision -> Expenses form)
# ---------------------------------------------------------------------------

RECEIPT_SYSTEM_PROMPT = (
    "You are an OCR and bookkeeping assistant for a small farm. You read photos "
    "of purchase bills, invoices and receipts for farm inputs. Extract only what "
    "is clearly visible and never invent values. Reply with JSON only."
)


def scan_receipt(image_path):
    """Read a bill photo and return expense fields.

    Returns {"ok": True, category, amount, date, description, confidence}
    or {"ok": False, "error": "..."}.
    """
    if not is_ai_configured():
        return {"ok": False, "error": "Set GEMINI_API_KEY to enable AI bill scanning."}
    if not image_path or not os.path.exists(image_path):
        return {"ok": False, "error": "That image could not be found."}

    try:
        import google.generativeai as genai
        from PIL import Image

        genai.configure(api_key=_get_api_key())
        model = genai.GenerativeModel(
            MODEL_NAME, system_instruction=RECEIPT_SYSTEM_PROMPT
        )
        prompt = (
            "Read this farm purchase bill/receipt and respond with a JSON object "
            "using exactly these keys:\n"
            "  category: one of " + ", ".join(db.EXPENSE_CATEGORIES) + "\n"
            "  amount: the grand total paid as a plain number (no currency symbol)\n"
            "  date: the bill date as YYYY-MM-DD (null if unreadable)\n"
            "  description: a short summary of the items and/or vendor\n"
            "  confidence: a number from 0 to 1 for how sure you are\n"
            "Use null for any field you cannot read. Do not guess."
        )
        image = Image.open(image_path)
        response = model.generate_content(
            [prompt, image],
            generation_config={"response_mime_type": "application/json"},
        )
        data = _parse_json(response.text)
    except Exception as exc:
        return {"ok": False, "error": f"Could not read the bill image: {exc}"}

    if not isinstance(data, dict):
        return {
            "ok": False,
            "error": "The AI could not read this bill. Please enter the details manually.",
        }

    amount = _to_float(data.get("amount"))
    if amount is not None and amount < 0:
        amount = abs(amount)

    return {
        "ok": True,
        "category": _closest_category(data.get("category")),
        "amount": amount,
        "date": _normalise_date(data.get("date")),
        "description": (data.get("description") or "").strip(),
        "confidence": _to_float(data.get("confidence")),
    }


# ---------------------------------------------------------------------------
# Feature 2: leaf-photo disease diagnosis (with consult fallback)
# ---------------------------------------------------------------------------

DIAGNOSIS_SYSTEM_PROMPT = (
    "You are a plant pathologist advising a small farmer. Analyse the leaf or "
    "plant photo and describe only what you can actually see. If the image is "
    "unclear, out of focus, or not a plant, say so. Never overstate your "
    "confidence or invent a disease. Reply with JSON only."
)


def diagnose_crop_disease(image_path, crop_name=None):
    """Analyse a leaf photo. Always returns a dict; flags low-confidence cases."""
    fallback = {
        "problem": "Uncertain",
        "severity": "Unknown",
        "treatment": "Isolate the affected plant, remove badly damaged leaves and "
                     "keep the area well ventilated until you have expert advice.",
        "confidence": 0.0,
        "consult_agronomist": True,
        "notes": "Not sure from this photo - consult a local agronomist before "
                 "applying any chemical treatment.",
    }

    if not is_ai_configured():
        fallback["notes"] = ("AI diagnosis needs a GEMINI_API_KEY. Not sure from "
                             "the photo - consult a local agronomist before treating.")
        return fallback
    if not image_path or not os.path.exists(image_path):
        fallback["notes"] = "No readable photo was provided - consult an agronomist."
        return fallback

    try:
        import google.generativeai as genai
        from PIL import Image

        genai.configure(api_key=_get_api_key())
        model = genai.GenerativeModel(
            MODEL_NAME, system_instruction=DIAGNOSIS_SYSTEM_PROMPT
        )
        crop_line = f"The farmer says this is a {crop_name} plant.\n" if crop_name else ""
        prompt = (
            crop_line +
            "Look at this leaf/plant photo and respond with a JSON object using "
            "exactly these keys:\n"
            "  problem: the most likely disease, pest or nutrient issue (short name)\n"
            "  severity: one of Low, Moderate, High or Unknown\n"
            "  treatment: 2-4 practical treatment steps for a small farm\n"
            "  confidence: a number from 0 to 1 for how sure you are\n"
            "  notes: a short caveat about the limits of a photo diagnosis\n"
            "If you are not confident, set severity to Unknown and confidence low."
        )
        image = Image.open(image_path)
        response = model.generate_content(
            [prompt, image],
            generation_config={"response_mime_type": "application/json"},
        )
        data = _parse_json(response.text)
    except Exception as exc:
        fallback["notes"] = f"Could not analyse the photo ({exc}). Consult an agronomist."
        return fallback

    if not isinstance(data, dict):
        return fallback

    confidence = _to_float(data.get("confidence"))
    if confidence is None:
        confidence = 0.0
    confidence = max(0.0, min(confidence, 1.0))

    severity = (data.get("severity") or "Unknown").strip().title()
    if severity not in ("Low", "Moderate", "High"):
        severity = "Unknown"

    problem = (data.get("problem") or "Uncertain").strip() or "Uncertain"
    treatment = (data.get("treatment") or "").strip()
    notes = (data.get("notes") or "").strip()

    problem_key = problem.lower()
    consult = (
        confidence < 0.55
        or severity == "Unknown"
        or problem_key in ("uncertain", "unknown", "unclear", "not sure", "healthy")
    )

    if consult:
        if problem_key not in ("uncertain", "unknown", "unclear", "not sure", "healthy"):
            problem = f"Possible: {problem}"
        if not treatment:
            treatment = ("Isolate the plant, remove affected leaves and avoid "
                         "overhead watering until you get expert advice.")
        if not notes:
            notes = ("Not sure from this photo - consult a local agronomist before "
                     "applying any treatment.")
    elif not notes:
        notes = "A photo diagnosis is indicative - confirm before treating a large area."

    return {
        "problem": problem,
        "severity": severity,
        "treatment": treatment,
        "confidence": confidence,
        "consult_agronomist": bool(consult),
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Feature 3: auto-generated crop calendar
# ---------------------------------------------------------------------------

CALENDAR_SYSTEM_PROMPT = (
    "You are an agronomist building a practical season calendar for a small farm "
    "near Mumbai, India. You give realistic, dated tasks for irrigation, "
    "fertilizer, pest/disease scouting and the harvest window. Reply with JSON only."
)

_DAYS_TO_HARVEST = {
    "wheat": 120, "corn": 90, "maize": 90, "tomato": 75, "potato": 90,
    "carrot": 75, "soybean": 100, "soyabean": 100, "rice": 120, "paddy": 120,
    "onion": 110, "cotton": 160, "sugarcane": 300, "groundnut": 120,
    "chilli": 90, "chili": 90, "brinjal": 100, "cabbage": 90, "spinach": 45,
    "cucumber": 60, "okra": 60, "banana": 300, "mango": 365, "grapes": 150,
}


def _days_to_harvest(crop_name):
    name = (crop_name or "").lower()
    for key, days in _DAYS_TO_HARVEST.items():
        if key in name:
            return days
    return 90


def _season_for(month):
    if month in (6, 7, 8, 9, 10):
        return "Kharif (monsoon)"
    if month in (11, 12, 1, 2, 3):
        return "Rabi (winter)"
    return "Zaid (summer)"


def _fallback_crop_calendar(crop_name, planting_date):
    """A sensible offline schedule so the feature works without an API key."""
    base = _to_iso_date(planting_date) or date.today()
    total = _days_to_harvest(crop_name)

    def due(offset):
        return (base + timedelta(days=offset)).isoformat()

    second_dose = min(45, max(30, total // 3))
    tasks = [
        ("Irrigation", "Check soil moisture & irrigate", 2,
         "Water deeply if the topsoil is dry. Adjust for any rainfall."),
        ("Irrigation", "Irrigation round", 10,
         "Repeat irrigation on the usual cycle; skip after heavy rain."),
        ("Fertilizer", "First fertilizer dose", 15,
         "Apply the first split dose of nitrogen as per your soil test."),
        ("Pest check", "Scout for pests & disease", 22,
         "Walk the field and inspect leaf undersides for early damage."),
        ("Irrigation", "Irrigation round", 25,
         "Maintain moisture during vegetative growth."),
        ("Fertilizer", "Second fertilizer dose", second_dose,
         "Top-dress with the second split dose at the active growth stage."),
        ("Pest check", "Pest & disease scouting", 50,
         "Check for caterpillars, aphids and leaf spots; treat at threshold."),
        ("Irrigation", "Irrigation round", 60,
         "Keep the crop stress-free as it approaches flowering."),
        ("Harvest", "Harvest window opens", total,
         "Crop should be mature - check grain/fruit readiness before cutting."),
        ("Harvest", "Harvest window closes", total + 14,
         "Finish harvesting before over-ripening or weather damage."),
    ]
    schedule = [
        {"task_type": t, "title": title, "due_date": due(offset), "notes": notes}
        for t, title, offset, notes in tasks
    ]
    schedule.sort(key=lambda t: t["due_date"])
    return schedule


def _ai_crop_calendar(crop_name, planting_date, area=None):
    import google.generativeai as genai

    genai.configure(api_key=_get_api_key())
    model = genai.GenerativeModel(
        MODEL_NAME, system_instruction=CALENDAR_SYSTEM_PROMPT
    )
    base = _to_iso_date(planting_date) or date.today()
    prompt = (
        f"Crop: {crop_name}\n"
        f"Planting date: {base.isoformat()}\n"
        f"Area: {area or 'not specified'}\n"
        f"Location: Mumbai region, India. Season: {_season_for(base.month)}.\n\n"
        "Build the care calendar. Respond with a JSON object with a single key "
        "\"tasks\" whose value is an array. Each task is an object with keys:\n"
        "  task_type: one of Irrigation, Fertilizer, Pest check, Harvest, Other\n"
        "  title: a short action, e.g. 'Apply first nitrogen dose'\n"
        "  due_date: YYYY-MM-DD, after the planting date\n"
        "  notes: one practical sentence of guidance\n"
        "Include recurring irrigation, at least two fertilizer doses, regular "
        "pest/disease checks and the harvest window. Return 6 to 10 tasks."
    )
    response = model.generate_content(
        prompt, generation_config={"response_mime_type": "application/json"}
    )
    data = _parse_json(response.text)
    if isinstance(data, dict):
        data = data.get("tasks")
    if not isinstance(data, list):
        return None

    cleaned = []
    for item in data[:12]:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        if not title:
            continue
        task_type = (item.get("task_type") or "Other").strip()
        if task_type not in db.TASK_TYPES:
            task_type = _closest_task_type(task_type)
        cleaned.append({
            "task_type": task_type,
            "title": title,
            "due_date": _normalise_date(item.get("due_date")),
            "notes": (item.get("notes") or "").strip(),
        })
    return cleaned or None


def generate_crop_calendar(crop_name, planting_date, area=None):
    """Return a list of task dicts for a crop, using Gemini when configured."""
    tasks = None
    if is_ai_configured():
        try:
            tasks = _ai_crop_calendar(crop_name, planting_date, area)
        except Exception:
            tasks = None
    if not tasks:
        tasks = _fallback_crop_calendar(crop_name, planting_date)
    return tasks