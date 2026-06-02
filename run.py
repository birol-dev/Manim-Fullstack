import os
import sys
import subprocess
import webbrowser
import threading
import time

def build_frontend():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    frontend_dir = os.path.join(root_dir, "frontend")
    dist_dir = os.path.join(frontend_dir, "dist")

    if not os.path.exists(dist_dir) or not os.path.exists(os.path.join(dist_dir, "index.html")):
        print("Frontend build not detected. Preparing plug-and-play build...")
        
        # Check node_modules
        node_modules = os.path.join(frontend_dir, "node_modules")
        if not os.path.exists(node_modules):
            print("Installing frontend dependencies (npm install)... This may take a moment.")
            subprocess.run("npm install", shell=True, cwd=frontend_dir, check=True)
            
        print("Building frontend (npm run build)...")
        subprocess.run("npm run build", shell=True, cwd=frontend_dir, check=True)
        print("Frontend built successfully!")

def open_browser():
    # Wait for Uvicorn to start up
    time.sleep(1.5)
    print("Opening web browser at http://localhost:8000...")
    webbrowser.open("http://localhost:8000")

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 1. Build frontend if necessary
    try:
        build_frontend()
    except Exception as e:
        print(f"Warning: Failed to build frontend: {e}")
        print("Please ensure Node.js and npm are installed. You can still run the backend server.")

    # 2. Launch browser in a separate thread
    threading.Thread(target=open_browser, daemon=True).start()

    # 3. Add backend directory to Python path and launch Uvicorn
    backend_dir = os.path.join(root_dir, "backend")
    sys.path.insert(0, backend_dir)
    
    import uvicorn
    print("Starting Manim Composer unified server on port 8000...")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=False)

if __name__ == "__main__":
    main()
