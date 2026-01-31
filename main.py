"""
AI Shopping Agent - Hybrid Backend (Database + Web Search + Personalization)
FastAPI server with PostgreSQL database primary search, Claude web search fallback, and user personalization
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import anthropic
import os
import json
import re
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from supabase import create_client, Client

app = FastAPI(title="AI Shopping Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
DATABASE_URL = os.environ.get("DATABASE_URL")

# Supabase configuration for user preferences
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = None

# Initialize Supabase client if credentials are available
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase client initialized")
    except Exception as e:
        print(f"⚠️ Supabase initialization failed: {e}")

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        print("Database connection error:", str(e))
        return None

def get_user_preferences(user_id: str):
    """Fetch user preferences from Supabase"""
    if not supabase:
        print("❌ Supabase client is None!")
        return None
    
    if not user_id:
        print("❌ No user_id provided!")
        return None
    
    try:
        print(f"🔍 Fetching preferences for user: {user_id}")
        response = supabase.table('user_profiles').select('*').eq('user_id', user_id).execute()
        print(f"📊 Supabase response: {response}")
        print(f"📊 Response data: {response.data}")
        
        if response.data and len(response.data) > 0:
            prefs = response.data[0]
            print(f"✅ Loaded preferences for user {user_id[:8]}...")
            print(f"✅ Favorite brands: {prefs.get('favorite_brands', [])}")
            return prefs
        else:
            print(f"⚠️ No data found for user {user_id}")
        return None
    except Exception as e:
        print(f"❌ Error fetching user preferences: {e}")
        import traceback
        traceback.print_exc()
        return None

def search_database(query: str, user_id: str = None):
    """Search database with optional personalization based on user preferences"""
    conn = get_db_connection()
    if not conn:
        print("No database connection available")
        return []
    
    try:
        cursor = conn.cursor()
        query_lower = query.lower()
        
        # Get user preferences if user_id is provided
        user_prefs = None
        if user_id:
            user_prefs = get_user_preferences(user_id)
        
        # Build base SQL query
        sql = """
            SELECT id, name, brand, price, color, fit, category, image_url, product_url, affiliate_link
            FROM products
            WHERE (LOWER(name) LIKE %s OR LOWER(brand) LIKE %s OR LOWER(color) LIKE %s OR LOWER(category) LIKE %s OR LOWER(fit) LIKE %s)
        """
        params = [f"%{query_lower}%"] * 5
        
        # Apply personalization filters if user preferences exist
        if user_prefs:
            print("🎯 Applying personalization filters...")
            
            # Filter by favorite brands
            favorite_brands = user_prefs.get('favorite_brands', [])
            if favorite_brands and len(favorite_brands) > 0:
                brand_placeholders = ','.join(['%s'] * len(favorite_brands))
                sql += f" AND (LOWER(REPLACE(brand, '\"', '')) IN ({brand_placeholders}) OR LOWER(brand) IN ({brand_placeholders}))"
                # Add each brand twice (once as-is, once for the replace check)
                brand_list = [brand.lower() for brand in favorite_brands]
                params.extend(brand_list + brand_list)
                print(f"   - Filtering by brands: {', '.join(favorite_brands)}")
            
            # Filter by favorite styles
            favorite_styles = user_prefs.get('favorite_styles', [])
            if favorite_styles and len(favorite_styles) > 0:
                style_placeholders = ','.join(['%s'] * len(favorite_styles))
                sql += f" AND LOWER(style) IN ({style_placeholders})"
                params.extend([style.lower() for style in favorite_styles])
                print(f"   - Filtering by styles: {', '.join(favorite_styles)}")
            
            # Filter by fit preferences based on category
            fit_prefs_tops = user_prefs.get('fit_preferences_tops', {})
            fit_prefs_bottoms = user_prefs.get('fit_preferences_bottoms', {})
            
            # Detect if query is for tops or bottoms
            top_keywords = ['shirt', 'top', 'hoodie', 'sweater', 'jacket', 'blouse', 'tshirt', 't-shirt', 'sweatshirt']
            bottom_keywords = ['jean', 'trouser', 'pant', 'short', 'skirt', 'chino', 'sweatpant']
            
            is_top_query = any(keyword in query_lower for keyword in top_keywords)
            is_bottom_query = any(keyword in query_lower for keyword in bottom_keywords)
            
            # Apply fit filters
            if is_top_query and fit_prefs_tops:
                # Collect all preferred fits from tops preferences
                preferred_fits = []
                for category_fits in fit_prefs_tops.values():
                    if isinstance(category_fits, list):
                        preferred_fits.extend(category_fits)
                
                if preferred_fits:
                    # Remove duplicates
                    preferred_fits = list(set(preferred_fits))
                    fit_placeholders = ','.join(['%s'] * len(preferred_fits))
                    sql += f" AND LOWER(fit) IN ({fit_placeholders})"
                    params.extend([fit.lower() for fit in preferred_fits])
                    print(f"   - Filtering by top fits: {', '.join(preferred_fits)}")
            
            elif is_bottom_query and fit_prefs_bottoms:
                # Collect all preferred fits from bottoms preferences
                preferred_fits = []
                for category_fits in fit_prefs_bottoms.values():
                    if isinstance(category_fits, list):
                        preferred_fits.extend(category_fits)
                
                if preferred_fits:
                    # Remove duplicates
                    preferred_fits = list(set(preferred_fits))
                    fit_placeholders = ','.join(['%s'] * len(preferred_fits))
                    sql += f" AND LOWER(fit) IN ({fit_placeholders})"
                    params.extend([fit.lower() for fit in preferred_fits])
                    print(f"   - Filtering by bottom fits: {', '.join(preferred_fits)}")
        
        sql += " LIMIT 50"
        
        print(f"🔍 Final SQL: {sql}")
        print(f"🔍 SQL Params: {params}")
        
        cursor.execute(sql, params)
        results = cursor.fetchall()
        
        products = []
        for row in results:
            product = dict(row)
            product['retailer'] = product.get('brand', 'Online Store')
            products.append(product)
        
        print(f"Database search found {len(products)} products{' (personalized)' if user_prefs else ''}")
        cursor.close()
        conn.close()
        return products
        
    except Exception as e:
        print("Database search error:", str(e))
        if conn:
            conn.close()
        return []

def search_products_with_claude(query: str):
    """Fallback web search using Claude (used when database has no results)"""
    prompt = f'Find real products for: "{query}"\n\nSearch the web and return 6 products as a JSON array. Each product needs: name, brand, price (USD number), color, fit, category, image_url, product_url, retailer. Return ONLY the JSON array. Start with [ and end with ].'
    
    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = ""
        for block in message.content:
            if block.type == "text":
                response_text += block.text
        
        if not response_text.strip():
            return []
        
        response_text = response_text.strip()
        response_text = re.sub(r'```json\s*', '', response_text)
        response_text = re.sub(r'```\s*$', '', response_text)
        response_text = response_text.strip()
        
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(0)
        
        products = json.loads(response_text)
        
        if not isinstance(products, list):
            return []
        
        for i, product in enumerate(products):
            product["id"] = f"web_{i + 1}"
            product.setdefault("name", "Unknown Product")
            product.setdefault("brand", "Unknown")
            product.setdefault("price", 0.0)
            product.setdefault("color", "N/A")
            product.setdefault("fit", "Regular")
            product.setdefault("category", "clothing")
            product.setdefault("retailer", "Online Store")
            product.setdefault("image_url", "https://via.placeholder.com/300x400?text=No+Image")
            product.setdefault("product_url", "#")
        
        return products
    except Exception as e:
        print("Error searching with Claude:", str(e))
        return []

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "AI Shopping Agent API (Hybrid: Database + Web Search + Personalization)",
        "version": "4.0.0",
        "timestamp": datetime.now().isoformat(),
        "features": ["database_search", "web_search_fallback", "user_personalization"]
    }

@app.post("/api/search")
async def search_products(request: Request):
    try:
        body = await request.json()
        query = body.get("query", "")
        user_id = body.get("user_id")  # Optional user ID for personalization
        
        if not query or len(query.strip()) == 0:
            raise HTTPException(status_code=400, detail="Query cannot be empty")
        
        print(f"\n{'='*50}")
        print(f"Search Query: {query}")
        if user_id:
            print(f"User ID: {user_id[:8]}... (personalized search)")
        print(f"{'='*50}")
        print("Step 1: Searching database...")
        
        # Search database with optional personalization
        db_products = search_database(query, user_id)
        
        if db_products and len(db_products) > 0:
            print(f"✅ Database returned {len(db_products)} products")
            return {
                "query": query,
                "total_results": len(db_products),
                "products": db_products,
                "source": "database",
                "personalized": user_id is not None and supabase is not None
            }
        
        print("⚠️ No database results. Falling back to web search...")
        web_products = search_products_with_claude(query)
        
        if not web_products or len(web_products) == 0:
            return {
                "query": query,
                "total_results": 0,
                "products": [],
                "source": "none",
                "personalized": False,
                "message": "No products found in database or web search. Try a different search."
            }
        
        print(f"✅ Web search returned {len(web_products)} products")
        return {
            "query": query,
            "total_results": len(web_products),
            "products": web_products,
            "source": "web_search",
            "personalized": False
        }
    except Exception as e:
        print("Search error:", str(e))
        raise HTTPException(status_code=500, detail="Search failed: " + str(e))

@app.post("/api/track")
async def track_interaction(request: Request):
    """
    Track user interactions with products (clicks, favorites, views)
    This data is used to learn user preferences and improve recommendations
    """
    try:
        body = await request.json()
        user_id = body.get("user_id")
        product_id = body.get("product_id")
        action = body.get("action")  # 'clicked', 'favorited', 'viewed'
        
        if not user_id or not product_id or not action:
            raise HTTPException(status_code=400, detail="user_id, product_id, and action are required")
        
        if not supabase:
            print("⚠️ Supabase not initialized, cannot track interaction")
            return {"success": False, "message": "Tracking not available"}
        
        # Save interaction to Supabase
        supabase.table('user_interactions').insert({
            'user_id': user_id,
            'product_id': str(product_id),
            'action': action
        }).execute()
        
        print(f"✅ Tracked: User {user_id[:8]}... {action} product {product_id}")
        return {"success": True}
        
    except Exception as e:
        print(f"Error tracking interaction: {e}")
        raise HTTPException(status_code=500, detail="Tracking failed: " + str(e))
    