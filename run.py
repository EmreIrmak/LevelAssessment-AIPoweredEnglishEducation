from dotenv import load_dotenv
import os

# Load environment variables from .env
load_dotenv()

from app import create_app

app = create_app()

if __name__ == '__main__':
    # debug=True is useful during development to see errors
    app.run(debug=True)