import os

import uvicorn

from .app import app

if __name__ == "__main__":
    port = int(os.environ.get("IRONGRAPH_PORT", "4870"))
    print(f"\n  ⚒️  IronGraph dashboard → http://localhost:{port}\n")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
