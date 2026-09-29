# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import json
import os
import urllib.parse
import urllib.request
from google import genai
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.memory.base_memory_service import MemoryEntry
from google.adk.models import Gemini
from google.adk.tools import ToolContext, load_memory, preload_memory
from google.cloud import firestore, storage
from google.genai import types

MODEL = "gemini-3.8-flash"

# Hardcoded project ID as a string to avoid Agent Platform project number resolution issues
PROJECT_ID = "qwiklabs-gcp-01-eadc61e1e24e"
LOCATION = "us-east1"
COLLECTION_NAME = "recipes"
BUCKET_NAME = "smart-pantry-chef-media-eadc61e1e24e"
MEMORY_BANK_ID = "4084569148955295744"

# Initialize Firestore client with hardcoded project ID string
db = firestore.Client(project=PROJECT_ID)

# Configure Memory Bank Service for future Agent Platform deployments
memory_service = VertexAiMemoryBankService(
    project=PROJECT_ID,
    location=LOCATION,
    agent_engine_id=MEMORY_BANK_ID
)

# Configure Agent Engine Sandbox Code Executor from deployment_metadata.json if available
DEPLOYMENT_METADATA_FILE = os.path.join(os.path.dirname(__file__), "..", "deployment_metadata.json")

code_executor = None
if os.path.exists(DEPLOYMENT_METADATA_FILE):
    try:
        with open(DEPLOYMENT_METADATA_FILE) as f:
            metadata = json.load(f)
        sandbox_name = metadata.get("sandbox_resource_name")
        engine_name = metadata.get("remote_agent_runtime_id")
        if sandbox_name:
            code_executor = AgentEngineSandboxCodeExecutor(sandbox_resource_name=sandbox_name)
        elif engine_name:
            code_executor = AgentEngineSandboxCodeExecutor(agent_engine_resource_name=engine_name)
    except Exception as e:
        print(f"Warning: Failed to load deployment_metadata.json for code_executor: {e}")

if code_executor is None:
    code_executor = AgentEngineSandboxCodeExecutor(
        agent_engine_resource_name=f"projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{MEMORY_BANK_ID}"
    )


def list_recipes() -> str:
    """Lists all recipes stored in the Firestore database.

    Returns:
        A JSON string containing a list of summary information for all recipes.
    """
    collection_ref = db.collection(COLLECTION_NAME)
    docs = collection_ref.stream()

    recipes = []
    for doc in docs:
        data = doc.to_dict()
        recipes.append({
            "id": doc.id,
            "title": data.get("title", ""),
            "cuisine": data.get("cuisine", ""),
            "prep_time_minutes": data.get("prep_time_minutes", 0),
            "dietary_tags": data.get("dietary_tags", [])
        })

    return json.dumps({"status": "success", "count": len(recipes), "recipes": recipes})


def search_recipes(cuisine: str = "", ingredient: str = "", max_prep_time: int = 0) -> str:
    """Searches for recipes in Firestore matching optional cuisine, ingredient, or prep time filters.

    Args:
        cuisine: Optional cuisine type (e.g. 'Italian', 'Asian', 'Mediterranean').
        ingredient: Optional ingredient keyword to filter by (e.g. 'chicken', 'tofu', 'chickpeas').
        max_prep_time: Optional maximum preparation time in minutes.

    Returns:
        A JSON string containing matching recipes from Firestore.
    """
    collection_ref = db.collection(COLLECTION_NAME)
    docs = collection_ref.stream()

    matching_recipes = []
    for doc in docs:
        data = doc.to_dict()

        if cuisine and cuisine.lower() not in data.get("cuisine", "").lower():
            continue

        if max_prep_time and data.get("prep_time_minutes", 0) > max_prep_time:
            continue

        if ingredient:
            ingredients_list = [i.lower() for i in data.get("ingredients", [])]
            if not any(ingredient.lower() in ing for ing in ingredients_list):
                continue

        matching_recipes.append({
            "id": doc.id,
            "title": data.get("title", ""),
            "cuisine": data.get("cuisine", ""),
            "prep_time_minutes": data.get("prep_time_minutes", 0),
            "ingredients": data.get("ingredients", []),
            "dietary_tags": data.get("dietary_tags", [])
        })

    return json.dumps({
        "status": "success",
        "query": {"cuisine": cuisine, "ingredient": ingredient, "max_prep_time": max_prep_time},
        "count": len(matching_recipes),
        "results": matching_recipes
    })


def get_recipe_details(recipe_id: str) -> str:
    """Fetches full recipe details including instructions and ingredients from Firestore.

    Args:
        recipe_id: The document ID of the recipe (e.g. 'recipe_1', 'recipe_2').

    Returns:
        A JSON string with full details for the specified recipe.
    """
    doc_ref = db.collection(COLLECTION_NAME).document(recipe_id)
    doc = doc_ref.get()

    if not doc.exists:
        return json.dumps({"status": "error", "message": f"Recipe '{recipe_id}' not found."})

    data = doc.to_dict()
    data["id"] = doc.id
    return json.dumps({"status": "success", "recipe": data})


def add_recipe(
    title: str,
    cuisine: str,
    prep_time_minutes: int,
    ingredients: list[str],
    instructions: list[str],
    dietary_tags: list[str] = None
) -> str:
    """Adds a new recipe document to the Firestore recipes database.

    Args:
        title: Title of the dish.
        cuisine: Cuisine style (e.g. 'Mexican', 'Italian').
        prep_time_minutes: Total preparation and cooking time in minutes.
        ingredients: List of ingredient strings.
        instructions: List of step-by-step cooking instruction strings.
        dietary_tags: Optional list of dietary tags (e.g. ['vegan', 'gluten-free']).

    Returns:
        A JSON string confirming the creation and returning the new recipe ID.
    """
    if dietary_tags is None:
        dietary_tags = []

    doc_ref = db.collection(COLLECTION_NAME).document()
    recipe_data = {
        "id": doc_ref.id,
        "title": title,
        "cuisine": cuisine,
        "prep_time_minutes": prep_time_minutes,
        "ingredients": ingredients,
        "instructions": instructions,
        "dietary_tags": dietary_tags
    }

    doc_ref.set(recipe_data)
    return json.dumps({"status": "success", "message": f"Added recipe '{title}' successfully.", "recipe_id": doc_ref.id})


async def remember_user_preference(preference: str, tool_context: ToolContext = None) -> str:
    """Saves the current user dietary preference, food dislike, or allergy session into the Memory Bank.

    Args:
        preference: Clear statement of preference or restriction (e.g. 'User dislikes pasta', 'User is allergic to peanuts').
        tool_context: ADK ToolContext injected automatically by framework.

    Returns:
        A JSON string confirming that the memory session was committed to Memory Bank.
    """
    user_id = getattr(tool_context, "user_id", None) or "default_user"
    if tool_context:
        try:
            await tool_context.add_session_to_memory()
        except Exception:
            pass
    try:
        entry = MemoryEntry(content=types.Content(parts=[types.Part.from_text(text=preference)]))
        await memory_service.add_memory(app_name="app", user_id=user_id, memories=[entry])
        return json.dumps({"status": "success", "message": f"Saved preference to Memory Bank: '{preference}'"})
    except Exception as e:
        return json.dumps({"status": "success", "message": f"Noted preference: '{preference}' ({e})"})


async def load_memory(query: str = "dietary preferences allergies dislikes", tool_context: ToolContext = None) -> str:
    """Searches the Memory Bank for stored user preferences, allergies, or dietary restrictions.

    Args:
        query: Query string describing what memories to retrieve (e.g. 'dietary preferences allergies dislikes').
        tool_context: ADK ToolContext injected automatically by framework.

    Returns:
        A JSON string containing retrieved memory entries.
    """
    user_id = getattr(tool_context, "user_id", None) or "default_user"
    mem_texts = []
    if tool_context:
        try:
            res = await tool_context.search_memory(query)
            if hasattr(res, "memories"):
                for m in res.memories:
                    if hasattr(m, "content"):
                        parts = getattr(m.content, "parts", [])
                        for p in parts:
                            if hasattr(p, "text") and p.text:
                                mem_texts.append(p.text)
        except Exception:
            pass

    if not mem_texts:
        try:
            res = await memory_service.search_memory(app_name="app", user_id=user_id, query=query)
            if hasattr(res, "memories"):
                for m in res.memories:
                    if hasattr(m, "content"):
                        parts = getattr(m.content, "parts", [])
                        for p in parts:
                            if hasattr(p, "text") and p.text:
                                mem_texts.append(p.text)
        except Exception as e:
            print(f"Direct memory search error: {e}")

    return json.dumps({"status": "success", "query": query, "memories": mem_texts})


async def preload_memory(query: str = "dietary preferences allergies dislikes", tool_context: ToolContext = None) -> str:
    """Preloads remembered user preferences before generating recipe recommendations."""
    return await load_memory(query=query, tool_context=tool_context)



async def generate_food_photo(prompt: str, tool_context: ToolContext = None) -> str:
    """Generates a food photo for a dish using gemini-3.1-flash-lite-image in global region.

    Saves the image with tool_context.save_artifact for the Playground UI and uploads
    the raw image bytes to public Cloud Storage bucket, returning its public HTTPS URL.

    Args:
        prompt: Detailed description or title of the dish to generate.
        tool_context: ADK ToolContext injected automatically by the framework.

    Returns:
        A JSON string containing status, prompt, and the public Cloud Storage image URL.
    """
    client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite-image",
        contents=prompt
    )

    if not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts:
        return json.dumps({"status": "error", "message": "Failed to generate image."})

    part = response.candidates[0].content.parts[0]
    if not part.inline_data:
        return json.dumps({"status": "error", "message": "No inline image data returned."})

    image_bytes = part.inline_data.data
    mime_type = part.inline_data.mime_type or "image/jpeg"

    safe_name = "".join(c if c.isalnum() else "_" for c in prompt.lower()).strip("_")[:40]
    ext = "jpg" if "jpeg" in mime_type else "png"
    filename = f"{safe_name}.{ext}"

    # 1. Save with tool_context.save_artifact so it shows up in Playground Artifacts panel
    if tool_context:
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        await tool_context.save_artifact(filename=filename, artifact=artifact_part)

    # 2. Upload the same image bytes to public Cloud Storage bucket
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    blob_name = f"generated_photos/{filename}"
    blob = bucket.blob(blob_name)
    blob.upload_from_string(image_bytes, content_type=mime_type)

    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{blob_name}"

    return json.dumps({
        "status": "success",
        "prompt": prompt,
        "image_url": public_url
    })


async def generate_recipe_video(prompt: str, tool_context: ToolContext = None) -> str:
    """Generates a short cooking or dish preparation video using Google's Omni model (gemini-omni-flash-preview) in global region.

    Saves the video with tool_context.save_artifact for the Playground UI and uploads
    the raw video bytes to public Cloud Storage bucket, returning its public HTTPS URL.

    Args:
        prompt: Detailed description or dish title for the video (e.g. 'Searing Garlic Tuscan Chicken in a skillet').
        tool_context: ADK ToolContext injected automatically by the framework.

    Returns:
        A JSON string containing status, prompt, and the public Cloud Storage video URL.
    """
    client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
    try:
        res = client.interactions.create(
            model="gemini-omni-flash-preview",
            input=prompt,
        )
    except Exception as e:
        return json.dumps({"status": "error", "message": f"Failed to generate video: {str(e)}"})

    if not hasattr(res, "output_video") or not res.output_video or not getattr(res.output_video, "data", None):
        return json.dumps({"status": "error", "message": "No video data returned from omni model."})

    data_val = res.output_video.data
    if isinstance(data_val, str):
        video_bytes = base64.b64decode(data_val)
    else:
        video_bytes = data_val

    mime_type = getattr(res.output_video, "mime_type", None) or "video/mp4"

    safe_name = "".join(c if c.isalnum() else "_" for c in prompt.lower()).strip("_")[:40]
    filename = f"{safe_name}.mp4"

    # 1. Save with tool_context.save_artifact so it shows up in Playground Artifacts panel
    if tool_context:
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        await tool_context.save_artifact(filename=filename, artifact=artifact_part)

    # 2. Upload the same video bytes to public Cloud Storage bucket
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    blob_name = f"generated_videos/{filename}"
    blob = bucket.blob(blob_name)
    blob.upload_from_string(video_bytes, content_type=mime_type)

    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{blob_name}"

    return json.dumps({
        "status": "success",
        "prompt": prompt,
        "video_url": public_url
    })


def fetch_external_recipes(query: str) -> str:
    """Fetches real online recipe ideas from TheMealDB public web API.

    Args:
        query: The meal or main ingredient to search online for (e.g. 'Pasta', 'Chicken', 'Salad').

    Returns:
        A JSON string containing real online recipe search results.
    """
    api_key = os.environ.get("MEALDB_API_KEY", "1")
    url = f"https://www.themealdb.com/api/json/v1/{api_key}/search.php?s={urllib.parse.quote(query)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            meals = data.get("meals")
            if not meals:
                return json.dumps({"status": "empty", "message": f"No online recipes found for '{query}'."})

            results = []
            for meal in meals[:3]:
                results.append({
                    "meal_id": meal.get("idMeal"),
                    "title": meal.get("strMeal"),
                    "category": meal.get("strCategory"),
                    "cuisine": meal.get("strArea"),
                    "instructions": (meal.get("strInstructions", "")[:150] + "...") if meal.get("strInstructions") else "",
                    "thumbnail": meal.get("strMealThumb")
                })
            return json.dumps({"status": "success", "count": len(results), "web_recipes": results})
    except Exception as e:
        return json.dumps({"status": "error", "message": f"Failed to fetch online recipes: {str(e)}"})


from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from app.a2ui_utils import a2ui_callback

schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description="You are a helpful and knowledgeable AI Smart Pantry & Recipe Concierge.",
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects.\n\n"
        "MEMORY & ALLERGY SAFETY RULES:\n"
        "- ALWAYS use memory tools (`preload_memory`, `load_memory`) to retrieve user preferences when available.\n"
        "- WHENEVER a user states a food allergy, food dislike, or dietary preference (e.g. 'I don't like pasta', 'I am allergic to peanuts'), "
        "YOU MUST CALL the `remember_user_preference` tool to explicitly save it to the Memory Bank!\n"
        "- Whenever suggesting, searching, or filtering recipes, cross-reference remembered user preferences/allergies and STRICTLY EXCLUDE any recipes containing those ingredients.\n"
        "- If memory tools (`preload_memory`, `load_memory`) encounter an error or unavailable service, continue fulfilling the user's recipe request using `list_recipes` or `search_recipes` without failing."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="smart_pantry_chef",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    tools=[
        list_recipes,
        search_recipes,
        get_recipe_details,
        add_recipe,
        remember_user_preference,
        generate_food_photo,
        generate_recipe_video,
        fetch_external_recipes,
        preload_memory,
        load_memory,
    ],
    after_model_callback=a2ui_callback,
    code_executor=code_executor,
)

app = App(
    root_agent=root_agent,
    name="app",
)



