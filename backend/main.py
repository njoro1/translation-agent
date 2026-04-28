from fastapi import FastAPI, WebSocket
import uvicorn

app = FastAPI(title="Translation Agent Backend")

@app.get("/")
async def health_check():
    return {"status": "ok", "message": "Translation Agent Backend is running"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_bytes()
            # Placeholder for processing logic
            await websocket.send_json({
                "text": "Transcription placeholder",
                "translation": "Translation placeholder",
                "timestamp": 0.0
            })
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket.close()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
