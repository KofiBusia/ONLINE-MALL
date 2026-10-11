"""Fixed reference data: categories, regions, statuses and the demo catalogue."""

CATEGORIES = [
    ("fashion", "Fashion"),
    ("food", "Food & drinks"),
    ("beauty", "Beauty"),
    ("home", "Home & craft"),
    ("elec", "Electronics"),
    ("farm", "Farm produce"),
]
CAT_LABELS = dict(CATEGORIES)

REGIONS = [
    "Ahafo", "Ashanti", "Bono", "Bono East", "Central", "Eastern", "Greater Accra",
    "North East", "Northern", "Oti", "Savannah", "Upper East", "Upper West",
    "Volta", "Western", "Western North",
]
DEFAULT_REGION = "Greater Accra"

ICONS = {
    "fashion": ["👗", "👕", "🧣", "👒", "👟", "👜", "📿", "💍", "🩴"],
    "food": ["🌶️", "🍌", "🥣", "🧃", "🍲", "🥜", "🍞"],
    "beauty": ["🧈", "🧼", "🧴", "💄", "🌸"],
    "home": ["🧺", "🪑", "🏺", "🕯️", "💼", "🛏️"],
    "elec": ["🔋", "💡", "🎧", "📱", "🔌", "💻"],
    "farm": ["🌿", "🫚", "🍅", "🥭", "🌽", "🥚"],
}
ALL_ICONS = {icon for icons in ICONS.values() for icon in icons}

SORTS = {
    "popular": "Best selling",
    "rating": "Top rated",
    "low": "Price: low to high",
    "high": "Price: high to low",
    "new": "Newest",
}

PAY_METHODS = {
    "momo": "Mobile Money",
    "card": "Visa or Mastercard",
    "cod": "Pay on delivery",
}

# Order life cycle. Money is held by Edwom until "released".
STATUS_FLOW = ["placed", "confirmed", "shipped", "delivered", "released"]
STATUS_LABELS = {
    "awaiting_payment": "Awaiting payment",
    "placed": "Order placed",
    "confirmed": "Shop confirmed",
    "shipped": "Out for delivery",
    "delivered": "Delivered",
    "released": "Shop paid",
    "disputed": "Under review",
    "cancelled": "Cancelled",
}
HELD_STATUSES = {"placed", "confirmed", "shipped", "delivered", "disputed"}
SELLER_NEXT = {"placed": "confirmed", "confirmed": "shipped", "shipped": "delivered"}
SELLER_ACTION_LABELS = {
    "placed": "Confirm order",
    "confirmed": "Mark out for delivery",
    "shipped": "Mark delivered",
}

AWNINGS = [
    ("var(--green)", "var(--gold)"),
    ("var(--red)", "#F6EBD3"),
    ("var(--black)", "var(--gold)"),
    ("var(--gold)", "var(--green)"),
    ("#2F4F8A", "#F6EBD3"),
]

# name, price (GH₵), category, icon, sold, rating, stock, description
DEMO_SHOPS = [
    {
        "name": "Adwoa's Kente House", "town": "Bonwire", "region": "Ashanti", "since": 2019, "verified": True,
        "about": "Third-generation weavers on the Bonwire loom. Custom names and years on request.",
        "products": [
            ("Handwoven kente stole", 350, "fashion", "🧣", 412, 4.9, 24, "Single-weave graduation stole, woven on a Bonwire loom. Can be personalised with a name or year; allow 5 extra days."),
            ("Ashanti wooden stool", 380, "home", "🪑", 96, 4.8, 9, "Hand-carved from a single block of sese wood. Each piece varies slightly in grain and finish."),
        ],
    },
    {
        "name": "Auntie Esi's Pantry", "town": "Cape Coast", "region": "Central", "since": 2021, "verified": True,
        "about": "Home-style sauces, drinks and staples, cooked in small batches.",
        "products": [
            ("Shito, hot pepper sauce 500g", 45, "food", "🌶️", 1840, 4.9, 120, "Slow-cooked with dried shrimp, herrings and ginger. Sealed jar, keeps for 3 months unopened."),
            ("Sobolo, 6 bottles", 48, "food", "🧃", 930, 4.7, 60, "Hibiscus drink with ginger, cloves and pineapple. No artificial colour."),
            ("Gari, extra crispy, 2kg", 38, "food", "🥣", 1210, 4.6, 200, "Roasted cassava granules, double-sieved. Good for soakings and eba."),
        ],
    },
    {
        "name": "Northern Gold Shea Co-op", "town": "Tamale", "region": "Northern", "since": 2018, "verified": True,
        "about": "A women's co-operative processing shea by hand in Tamale.",
        "products": [
            ("Unrefined shea butter, 1kg", 85, "beauty", "🧈", 2205, 4.9, 150, "Grade A, hand-processed. Ivory colour, nutty scent."),
            ("Alata samina black soap, 3 pack", 60, "beauty", "🧼", 1380, 4.8, 90, "Traditional black soap made with plantain peel ash, palm kernel oil and shea."),
        ],
    },
    {
        "name": "Bolga Weavers Collective", "town": "Bolgatanga", "region": "Upper East", "since": 2020, "verified": True,
        "about": "Baskets and hats woven from elephant grass and veta vera straw.",
        "products": [
            ("Bolga market basket, large", 220, "home", "🧺", 340, 4.9, 30, "Elephant-grass basket with leather-wrapped handle. Holds up to 15kg."),
            ("Woven straw sun hat", 95, "fashion", "👒", 210, 4.6, 40, "Wide-brim hat woven from veta vera straw. Packs flat and springs back into shape."),
        ],
    },
    {
        "name": "Kantamanto Threads", "town": "Accra", "region": "Greater Accra", "since": 2022, "verified": True,
        "about": "Made-to-wear African print clothing, cut and sewn in Accra.",
        "products": [
            ("Ankara wrap dress", 260, "fashion", "👗", 520, 4.7, 35, "Midi wrap dress in 100% cotton wax print. Sizes 8 to 20; custom sizing on request."),
            ("Batik short-sleeve shirt", 190, "fashion", "👕", 388, 4.6, 42, "Hand-dyed batik on cotton, relaxed fit. Ideal for Friday wear."),
        ],
    },
    {
        "name": "Krobo Bead Studio", "town": "Somanya", "region": "Eastern", "since": 2017, "verified": True,
        "about": "Powder-glass beads fired in clay moulds, the Krobo way.",
        "products": [
            ("Krobo glass bead necklace", 120, "fashion", "📿", 610, 4.9, 55, "Each strand is one of a kind."),
            ("Recycled glass bead bracelets, set of 5", 75, "fashion", "💍", 455, 4.7, 80, "Stackable elastic bracelets made from recycled bottle glass."),
        ],
    },
    {
        "name": "Circle Gadgets", "town": "Accra", "region": "Greater Accra", "since": 2023, "verified": True,
        "about": "Power, lighting and phone accessories with a 6-month warranty.",
        "products": [
            ("Power bank 20,000mAh", 210, "elec", "🔋", 1460, 4.5, 70, "Fast charging, two USB-A and one USB-C port. 6-month warranty."),
            ("Solar rechargeable lamp", 165, "elec", "💡", 890, 4.6, 65, "Charges by sun or USB, three brightness levels, up to 30 hours of light."),
        ],
    },
    {
        "name": "Ho Agro Fresh", "town": "Ho", "region": "Volta", "since": 2025, "verified": False,
        "about": "Produce and snacks from farms in the Volta highlands.",
        "products": [
            ("Moringa leaf powder, 250g", 40, "farm", "🌿", 300, 4.5, 110, "Shade-dried and stone-milled. Add to soups, smoothies or tea."),
            ("Plantain chips, 10 packs", 55, "food", "🍌", 760, 4.6, 140, "Thin-sliced ripe and unripe plantain chips, lightly salted."),
            ("Fresh ginger, 5kg sack", 70, "farm", "🫚", 240, 4.4, 50, "Ships within 48 hours of harvest."),
        ],
    },
    {
        "name": "Suame Leather Works", "town": "Kumasi", "region": "Ashanti", "since": 2016, "verified": True,
        "about": "Hand-stitched leather goods from locally tanned hides.",
        "products": [
            ("Ahenema leather sandals", 180, "fashion", "🩴", 470, 4.8, 38, "Hand-stitched in Suame. Sizes 38 to 46."),
            ("Leather laptop bag", 450, "home", "💼", 150, 4.8, 14, "Fits 15-inch laptops. Padded compartment, brass fittings, adjustable strap."),
        ],
    },
]

# Fallback picture for products without photos
CATEGORY_ICON = {key: icons[0] for key, icons in ICONS.items()}

APPLICATION_STATUSES = {"new": "New", "approved": "Approved", "rejected": "Declined"}
