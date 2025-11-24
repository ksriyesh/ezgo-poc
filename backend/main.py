"""
Main entry point to run the FastAPI server.

Usage:
    python main.py
    
Or with uv:
    uv run python main.py
"""
import sys
import uvicorn

if __name__ == "__main__":
    # Set UTF-8 encoding for Windows console
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except AttributeError:
            import io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    
    print("🚀 Starting ezGO POC Backend Server...")
    print("📍 API will be available at: http://localhost:8000")
    print("📖 API docs at: http://localhost:8000/docs")
    print("📊 Alternative docs at: http://localhost:8000/redoc")
    print("\nPress CTRL+C to stop the server\n")
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )



