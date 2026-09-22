import db
from datetime import date, timedelta


def seed_database():
    db.init_db()

    created = {"crops": 0, "inventory": 0, "sales": 0, "expenses": 0}

    # Keep the demo account and sample records safe to seed repeatedly.
    db.create_user("yaswanth", "12345678")

    crops = [
        ("Wheat", "10 acres", "Growing", 20),
        ("Corn", "15 acres", "Harvested", -5),
        ("Tomatoes", "2 acres", "Planted", 60),
        ("Potatoes", "5 acres", "Growing", 35),
        ("Carrots", "1 acre", "Growing", 25),
        ("Soybeans", "20 acres", "Harvested", -10),
        ("Rice", "12 acres", "Growing", 50),
        ("Onions", "3 acres", "Ready", 8),
        ("Cotton", "18 acres", "Planted", 90),
        ("Chili Peppers", "2 acres", "Growing", 40),
        ("Groundnuts", "6 acres", "Growing", 30),
        ("Spinach", "0.5 acre", "Ready", 5),
    ]

    for name, area, status, harvest_in_days in crops:
        planting_date = (date.today() - timedelta(days=45)).isoformat()
        harvest_date = (date.today() + timedelta(days=harvest_in_days)).isoformat()
        if not any(c["name"] == name for c in db.get_crops()):
            db.add_crop(name, area, planting_date, status, harvest_date)
            created["crops"] += 1

    crop_ids = {c["name"]: c["id"] for c in db.get_crops()}

    inventory_items = [
        ("Urea Fertilizer", 50, "bags", 20),
        ("Tractor Fuel", 200, "L", 50),
        ("Tomato Seeds", 5, "kg", 10),
        ("Pesticide", 10, "L", 15),
        ("Empty Sacks", 500, "units", 100),
        ("Shovels", 10, "units", 2),
        ("Rice Seeds", 25, "kg", 8),
        ("Onion Seedlings", 1200, "units", 300),
        ("Drip Lines", 8, "rolls", 2),
        ("Compost", 80, "bags", 20),
        ("Gloves", 18, "pairs", 5),
        ("Harvest Crates", 40, "units", 10),
        ("Weed Control", 6, "L", 8),
    ]

    existing_inventory = {item["item_name"] for item in db.get_inventory()}
    for name, qty, unit, threshold in inventory_items:
        if name not in existing_inventory:
            db.add_inventory_item(name, qty, unit, threshold)
            created["inventory"] += 1

    sales = [
        ("Wheat", 100, 25.50),
        ("Corn", 500, 15.00),
        ("Soybeans", 200, 30.00),
        ("Tomatoes", 50, 40.00),
        ("Potatoes", 180, 22.00),
        ("Carrots", 75, 35.00),
        ("Onions", 220, 28.00),
        ("Spinach", 45, 18.00),
        ("Rice", 300, 32.00),
        ("Groundnuts", 90, 55.00),
    ]

    existing_sales = {
        (sale["crop_name"], sale["quantity"], sale["price"])
        for sale in db.get_sales()
    }
    for index, (crop, qty, price) in enumerate(sales):
        if (crop, qty, price) not in existing_sales:
            sale_date = (date.today() - timedelta(days=index + 1)).isoformat()
            db.add_sale(crop, qty, price, sale_date, crop_ids.get(crop))
            created["sales"] += 1

    expenses = [
        ("Seeds", 5000, "Bought tomato seeds", "Tomatoes"),
        ("Fertilizer", 12000, "Urea for wheat field", "Wheat"),
        ("Fuel", 3000, "Tractor fuel", None),
        ("Labor", 8000, "Harvesting labor", "Corn"),
        ("Maintenance", 2500, "Tractor oil change", None),
        ("Irrigation", 4500, "Drip irrigation repair", "Rice"),
        ("Pesticide", 2800, "Crop protection for chili field", "Chili Peppers"),
        ("Fertilizer", 6200, "Compost and nutrients for vegetables", "Potatoes"),
        ("Transport", 3800, "Produce delivery to local market", "Onions"),
        ("Labor", 5200, "Weeding and field preparation", "Cotton"),
        ("Equipment", 7500, "Harvest crates and tools", None),
        ("Seeds", 2100, "Rice and groundnut seed stock", "Groundnuts"),
    ]

    existing_expenses = {
        (expense["category"], expense["amount"], expense["description"])
        for expense in db.get_expenses()
    }
    for index, (cat, amount, desc, crop) in enumerate(expenses):
        if (cat, amount, desc) not in existing_expenses:
            exp_date = (date.today() - timedelta(days=index + 1)).isoformat()
            db.add_expense(cat, amount, exp_date, desc, crop_ids.get(crop))
            created["expenses"] += 1

    profit_sales = [
        ("Rice", 700, 45.00),
        ("Onions", 500, 50.00),
        ("Tomatoes", 400, 65.00),
        ("Potatoes", 500, 35.00),
    ]
    existing_sales = {
        (sale["crop_name"], sale["quantity"], sale["price"])
        for sale in db.get_sales()
    }
    if db.get_total_profit() <= 0:
        for index, (crop, qty, price) in enumerate(profit_sales):
            if (crop, qty, price) not in existing_sales:
                sale_date = (date.today() - timedelta(days=index + 10)).isoformat()
                db.add_sale(crop, qty, price, sale_date, crop_ids.get(crop))
                created["sales"] += 1

    print(
        "Sample data ready. Added: "
        + ", ".join(f"{count} {name}" for name, count in created.items() if count)
        if any(created.values()) else "Sample data already exists; nothing added."
    )


if __name__ == "__main__":
    seed_database()
