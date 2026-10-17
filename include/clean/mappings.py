"""Label standardization maps.

Keys are normalized with `common.norm_key` (strip, lowercase, collapse spaces), so list
only the lowercase form. Built from the distinct values seen in the profiling notebook.
Anything NOT listed here becomes "Unknown" and is counted in the run stats
(`unmapped_<column>`), so new spellings show up instead of disappearing.

Lines marked DECISION are judgement calls the team should confirm and write down in
docs/cleaning_rules.md.
"""

CATEGORY = {
    "mobile & accessories": "Mobile & Accessories", "mobile and accessories": "Mobile & Accessories",
    "mobile acc.": "Mobile & Accessories", "mobiles": "Mobile & Accessories",
    "footwear": "Footwear", "shoes": "Footwear",
    "fashion": "Fashion", "clothing": "Fashion", "fashion & apparel": "Fashion",
    "sports": "Sports & Outdoors", "sports & outdoors": "Sports & Outdoors",
    "sports and outdoors": "Sports & Outdoors",
    "automotive": "Automotive", "auto": "Automotive", "car accessories": "Automotive",
    "health & wellness": "Health & Wellness", "health and wellness": "Health & Wellness",
    "health": "Health & Wellness",
    "electronics": "Electronics", "elec.": "Electronics", "electronic items": "Electronics",
    "grocery": "Grocery", "groceries": "Grocery", "food & grocery": "Grocery",  # DECISION: canonical name
    "home & kitchen": "Home & Kitchen", "home and kitchen": "Home & Kitchen",
    "home&kitchen": "Home & Kitchen",
    "toys & games": "Toys & Games", "toys and games": "Toys & Games", "toys": "Toys & Games",
    "beauty & personal care": "Beauty & Personal Care", "beauty and personal care": "Beauty & Personal Care",
    "beauty": "Beauty & Personal Care", "personal care": "Beauty & Personal Care",
    "books & stationery": "Books & Stationery", "books and stationery": "Books & Stationery",
    "books": "Books & Stationery", "stationary": "Books & Stationery",
}

ORDER_STATUS = {
    "delivered": "Delivered", "deliverd": "Delivered", "completed": "Delivered", "complete": "Delivered",
    "cancelled": "Cancelled", "canceled": "Cancelled",
    "returned": "Returned", "return": "Returned",
    "in transit": "In Transit", "in-transit": "In Transit",
    "shipped": "In Transit",  # DECISION: Shipped = not yet delivered = In Transit
}

DELIVERY_STATUS = {
    "delivered": "Delivered", "deliverd": "Delivered", "completed": "Delivered", "complete": "Delivered",
    "returned to seller": "Returned to Seller", "return to seller": "Returned to Seller", "rto": "Returned to Seller",
    "in transit": "In Transit", "in-transit": "In Transit",
    "shipped": "In Transit",  # DECISION
}

CHANNEL = {
    "web": "Web", "website": "Web",
    "app": "App", "mobile app": "App",
    "mobile web": "Mobile Web", "mweb": "Mobile Web",
}

PAYMENT_METHOD = {
    "cod": "COD", "cash on delivery": "COD",
    "jazzcash": "JazzCash", "jazz cash": "JazzCash",
    "easypaisa": "EasyPaisa", "easy paisa": "EasyPaisa",
    "card": "Card", "debit card": "Card", "credit/debit card": "Card",  # DECISION: merge debit and credit
    "bank transfer": "Bank Transfer", "bank trf": "Bank Transfer",
}

PAYMENT_STATUS = {
    "paid": "Paid", "complete": "Paid", "success": "Paid",  # DECISION: Complete/Success = Paid
    "cancelled": "Cancelled", "canceled": "Cancelled",
    "refunded": "Refunded", "refund": "Refunded",
    "pending": "Pending",
}

RETURN_STATUS = {
    "refunded": "Refunded", "refund": "Refunded",
    "approved": "Approved",
    "rejected": "Rejected", "declined": "Rejected",  # Rejected = not a valid return (brief)
}

RETURN_REASON = {
    "not as described": "Not as described", "different from picture": "Not as described",
    "size/fit issue": "Size/fit issue", "size/fit": "Size/fit issue", "doesn't fit": "Size/fit issue",
    "wrong size": "Size/fit issue", "size issue": "Size/fit issue",
    "quality issue": "Quality issue", "bad quality": "Quality issue", "quality": "Quality issue",
    "poor quality": "Quality issue",
    "wrong item delivered": "Wrong item delivered", "wrong item": "Wrong item delivered",
    "received wrong product": "Wrong item delivered",
    "wrong colour": "Wrong colour", "colour mismatch": "Wrong colour", "color mismatch": "Wrong colour",
    "colour different": "Wrong colour",
    "damaged product": "Damaged product", "damaged": "Damaged product", "item damaged": "Damaged product",
    "late delivery": "Late delivery", "delivered late": "Late delivery", "late": "Late delivery",
    "too late": "Late delivery",
    "changed mind": "Changed mind", "no longer needed": "Changed mind", "changed my mind": "Changed mind",
    "change of mind": "Changed mind",
    "missing parts": "Missing parts", "incomplete": "Missing parts", "missing part": "Missing parts",
    "parts missing": "Missing parts",
}

COURIER = {
    "m&p": "M&P", "mnp": "M&P", "m & p": "M&P",
    "leopards": "Leopards", "leopard courier": "Leopards",
    "postex": "PostEx",
    "tcs express": "TCS", "tcs": "TCS", "t.c.s": "TCS",
    "blueex": "BlueEx", "blue-ex": "BlueEx", "blue ex": "BlueEx",
    "trax": "Trax",
}

PROVINCE = {
    "sindh": "Sindh", "sind": "Sindh",
    "punjab": "Punjab", "panjab": "Punjab",
    "balochistan": "Balochistan", "baluchistan": "Balochistan",
    "khyber pakhtunkhwa": "Khyber Pakhtunkhwa", "kp": "Khyber Pakhtunkhwa", "kpk": "Khyber Pakhtunkhwa",
    "gilgit-baltistan": "Gilgit-Baltistan", "gilgit baltistan": "Gilgit-Baltistan", "gb": "Gilgit-Baltistan",
    "azad kashmir": "Azad Kashmir", "azad jammu & kashmir": "Azad Kashmir",
    "islamabad": "Islamabad",
}

GENDER = {"m": "M", "male": "M", "f": "F", "female": "F"}

SELLER_TIER = {"gold": "Gold", "silver": "Silver", "bronze": "Bronze"}
