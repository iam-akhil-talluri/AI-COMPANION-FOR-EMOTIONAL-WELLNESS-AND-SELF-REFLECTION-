"""Start the backend with `python main.py` (run from the backend folder)."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
