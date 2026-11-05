"""Real child/HTTP fixture; redirects only synthetic requests to a local server."""
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import aurora_chatgpt_transport as transport
from aurora_subscription_worker import worker_main

if __name__ == "__main__":
    target = urlsplit(sys.argv[1])
    assert target.scheme == "http" and target.hostname == "127.0.0.1" and target.port
    transport.RESOURCE = sys.argv[1]
    worker_main()
