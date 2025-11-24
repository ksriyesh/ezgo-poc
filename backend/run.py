"""
Run the FastAPI application with proper configuration.
"""
import uvicorn
import sys

if __name__ == "__main__":
    print("🚀 Starting FastAPI server...", flush=True)
    print(f"Python: {sys.executable}", flush=True)
    print(f"Port: 8085", flush=True)
    print("-" * 50, flush=True)
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8085,
        reload=False,  # Disabled to prevent infinite reload loop on Windows
    )

