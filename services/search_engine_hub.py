import requests
import json
import random
import os

# List of public SearXNG instances (Rotating list to avoid downtime)
# In production, you should HOST your own instance for 100% privacy and control.
# Docker command: docker run -d -p 8080:8080 searxng/searxng
PUBLIC_SEARX_INSTANCES = [
    "https://searx.be/search",
    "https://searx.space/search",
    "https://search.mdosch.de/search"
]

def search_web_unlimited(query, max_results=5):
    """
    Uses SearXNG to fetch results from Google, Bing, DDG, etc. simultaneously.
    No API Key required. No Rate Limits (if self-hosted).
    """
    params = {
        "q": query,
        "format": "json",
        "language": "en-US",
        "engines": "google,bing,duckduckgo,yahoo",  # The "Big 4"
    }

    # Try instances until one works
    for base_url in PUBLIC_SEARX_INSTANCES:
        try:
            print(f"      🌍 Routing query via {base_url}...")
            response = requests.get(base_url, params=params, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])[:max_results]
                
                # Format into a clean string for the LLM
                clean_results = []
                for r in results:
                    title = r.get("title", "No Title")
                    snippet = r.get("content", "No content")
                    source = r.get("url", "Unknown URL")
                    clean_results.append(f"SOURCE: {title} ({source})\nCONTENT: {snippet}\n")
                
                return "\n".join(clean_results)
                
        except Exception as e:
            print(f"      ⚠️ Instance failed: {e}. Switching...")
            continue
    
    return None # If all fail

if __name__ == "__main__":
    # Test it
    print(search_web_unlimited("Latest suppliers for Apple Inc 2025"))