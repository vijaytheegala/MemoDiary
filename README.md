# MemoDiary V3 - Personal AI Life Companion

A sophisticated, private, and empathetic AI diary that remembers your life. MemoDiary is an asynchronous, Single-Page personal companion application I built to tackle the LLM Amnesia problem. It utilizes FastAPI on the backend and pure Vanilla JavaScript on the frontend. The core innovation is its decoupling of live conversational Generation from background Memory Extraction. When a user speaks via the browser's MediaRecorder API, a custom Intent Routing layer filters the query to ensure we aren't wasting LLM tokens or SQLite reads on trivial prompts like math. If it is personal, the backend searches a structured, persistent SQLite 'knowledge graph', injects context, and streams text back to the browser using Server-Sent Events, where JS sequentially maps it onto an async audio queue for Text-To-Speech playback. I built it specifically to maximize low-latency, scalable AI interaction without expensive NoSQL clouds, demonstrating full-stack proficiency from complex prompt engineering down to bare-metal database index optimization.


## 📋 Prerequisites

- **Python 3.8+** installed on your system.
- A **Google Gemini API Key** (Get one from [Google AI Studio](https://aistudio.google.com/)).

## 🚀 Installation

1.  **Clone/Download the Repository**
    Navigate to the project folder in your terminal:
    ```bash
    cd "path/to/MemoDiary web V3"
    ```

2.  **Create a Virtual Environment (Recommended)**
    To keep dependencies isolated:
    ```bash
    # Windows
    python -m venv venv
    venv\Scripts\activate

    # Mac/Linux
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

## ⚙️ Configuration

1.  **Create a `.env` file** in the root directory (if not exists).
2.  **Add the following secrets** to the `.env` file:

    ```env
    # Required: Your Google Gemini API Key
    GEMINI_API_KEY=your_actual_api_key_here

    # Optional: Secure Admin PIN Hash (Default provided for dev)
    # To generate your own: 
    #   Run python -c "import hashlib, os; salt = os.urandom(16).hex(); pin = '123456'; idx = hashlib.pbkdf2_hmac('sha256', pin.encode(), bytes.fromhex(salt), 100000).hex(); print(f'ADMIN_SALT_HEX={salt}\nADMIN_PIN_HASH_HEX={idx}')"
    ADMIN_SALT_HEX=7d808147a534abdcd708343e801868e7
    ADMIN_PIN_HASH_HEX=8d2c5f5d5458e6c44d208a4df2665419b483bacbd4312815c99c4b26aca624cf
    ```
    *(Note: The default PIN for the above hash is `148314`)*

## ▶️ Running the Application

1.  **Start the Server**
    Run the following command in your terminal:
    ```bash
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    ```
    *(The `--reload` flag auto-restarts the server when you change code during development. For production, omit it.)*

2.  **Access the App**
    Open your web browser and go to:
    👉 **[http://localhost:8000](http://localhost:8000)**

## 🧪 Verification & Testing

To ensure everything is working correctly (Backend logic, Admin login, Health check):

1.  Run the verification script:
    ```bash
    python tests/verify_production.py
    ```

## 🛡️ Admin Panel

- Access Admin Stats (API) at `/api/admin/stats`.
- Requires Authentication (PIN-based exchange).
- *Currently, the admin panel is primarily an API interface.*

## 📂 Project Structure

- `app/`: Backend logic (FastAPI, AI, Memory, Storage).
- `static/`: Frontend (HTML, CSS, JS).
- `memodiary.db`: SQLite database (auto-created).
- `logs/`: Application logs.
