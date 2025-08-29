import uvicorn
import os
from pathlib import Path
from app import create_app
from app.config import config

app = create_app()

def create_self_signed_cert():
    """Create self-signed certificates for development HTTPS"""
    cert_dir = Path("certs")
    cert_dir.mkdir(exist_ok=True)
    
    cert_file = cert_dir / "cert.pem"
    key_file = cert_dir / "key.pem"
    
    # Only create if they don't exist
    if not cert_file.exists() or not key_file.exists():
        print("Creating self-signed certificates for development...")
        os.system(f'openssl req -x509 -newkey rsa:4096 -keyout {key_file} -out {cert_file} -days 365 -nodes -subj "/C=US/ST=State/L=City/O=Development/CN=localhost"')
        print("Self-signed certificates created!")
    
    return str(cert_file), str(key_file)

if __name__ == "__main__":
    if config.ENV == "development":
        # Check if user wants HTTPS
        use_https = os.getenv("USE_HTTPS", "false").lower() == "true"
        
        if use_https:
            cert_file, key_file = create_self_signed_cert()
            uvicorn.run(
                "run:app",
                host="0.0.0.0",
                port=8000,
                reload=config.DEBUG,
                log_level="debug",
                ssl_certfile=cert_file,
                ssl_keyfile=key_file
            )
        else:
            uvicorn.run(
                "run:app",
                host="0.0.0.0",
                port=8000,
                reload=config.DEBUG,
                log_level="debug"
            )
    else:
        uvicorn.run(
            "run:app",
            host="0.0.0.0",
            port=8000,
            reload=False,
            log_level="debug"
        )
