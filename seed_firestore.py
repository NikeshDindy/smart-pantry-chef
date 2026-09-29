import logging
from google.cloud import firestore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_firestore")

# Hardcoded project ID as required to avoid project number resolution issues on Agent Platform
PROJECT_ID = "qwiklabs-gcp-01-eadc61e1e24e"
COLLECTION_NAME = "recipes"

SEED_RECIPES = [
    {
        "id": "recipe_1",
        "title": "Creamy Garlic Tuscan Chicken",
        "cuisine": "Italian",
        "prep_time_minutes": 25,
        "ingredients": [
            "chicken breast",
            "heavy cream",
            "spinach",
            "sun-dried tomatoes",
            "garlic",
            "olive oil",
            "parmesan cheese"
        ],
        "instructions": [
            "Sear chicken breasts in olive oil until golden.",
            "Sauté garlic and sun-dried tomatoes.",
            "Pour in heavy cream and simmer with spinach and parmesan.",
            "Return chicken to pan and serve warm."
        ],
        "dietary_tags": ["keto", "gluten-free", "high-protein"]
    },
    {
        "id": "recipe_2",
        "title": "Quick Tofu & Vegetable Stir-Fry",
        "cuisine": "Asian",
        "prep_time_minutes": 15,
        "ingredients": [
            "firm tofu",
            "broccoli",
            "bell peppers",
            "soy sauce",
            "sesame oil",
            "ginger",
            "garlic"
        ],
        "instructions": [
            "Cube tofu and pan-fry in sesame oil until crispy.",
            "Stir-fry broccoli and bell peppers with minced ginger and garlic.",
            "Toss tofu with vegetables and soy sauce.",
            "Serve immediately over rice or cauliflower rice."
        ],
        "dietary_tags": ["vegan", "vegetarian", "dairy-free"]
    },
    {
        "id": "recipe_3",
        "title": "Mediterranean Chickpea & Cucumber Salad",
        "cuisine": "Mediterranean",
        "prep_time_minutes": 10,
        "ingredients": [
            "canned chickpeas",
            "cucumber",
            "cherry tomatoes",
            "feta cheese",
            "red onion",
            "olive oil",
            "lemon juice"
        ],
        "instructions": [
            "Rinse and drain chickpeas.",
            "Dice cucumber, cherry tomatoes, and red onion.",
            "Combine all ingredients in a bowl with olive oil, lemon juice, and crumbled feta."
        ],
        "dietary_tags": ["vegetarian", "gluten-free", "quick"]
    },
    {
        "id": "recipe_4",
        "title": "Avocado & Black Bean Burrito Bowl",
        "cuisine": "Mexican",
        "prep_time_minutes": 20,
        "ingredients": [
            "black beans",
            "avocado",
            "brown rice",
            "corn",
            "salsa",
            "cilantro",
            "lime juice"
        ],
        "instructions": [
            "Cook brown rice and warm black beans and corn.",
            "Slice fresh avocado.",
            "Assemble bowls with rice, beans, corn, avocado, and top with salsa and fresh lime."
        ],
        "dietary_tags": ["vegan", "vegetarian", "high-fiber"]
    }
]


def seed_database():
    logger.info(f"Connecting to Firestore with project ID: {PROJECT_ID}")
    db = firestore.Client(project=PROJECT_ID)
    collection_ref = db.collection(COLLECTION_NAME)

    for recipe in SEED_RECIPES:
        doc_id = recipe["id"]
        doc_ref = collection_ref.document(doc_id)
        doc_ref.set(recipe)
        logger.info(f"Seeded recipe: {recipe['title']} (ID: {doc_id})")

    logger.info("Firestore seeding completed successfully.")


if __name__ == "__main__":
    seed_database()
