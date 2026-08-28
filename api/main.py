from api.app import app

def main():
    """Khoi dong FastAPI khi chay `python -m api.main`."""
    import uvicorn

    uvicorn.run("api.app:app", host="0.0.0.0", port=8000, reload=False)

if __name__ == "__main__":
    main()
